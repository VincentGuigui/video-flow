"""Hardware video decode/encode probing with one-frame test runs, ordered with software fallback."""

from __future__ import annotations

import glob
import sys
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from videoflow.media.caps import FFmpegCaps, run_sync

Runner = Callable[[list[str]], bool]
Codec = str  # "h264" | "hevc"

SOFTWARE_ENCODERS: dict[Codec, str] = {"h264": "libx264", "hevc": "libx265"}
TEST_SIZE = "640x360"


@dataclass(frozen=True)
class DecodeOption:
    """A hardware decode method: `-hwaccel <hwaccel>` plus optional device args."""

    name: str  # vendor-ish label: nvidia, intel_qsv, vaapi, d3d11va
    hwaccel: str
    device_args: tuple[str, ...] = ()

    def input_args(self) -> list[str]:
        return ["-hwaccel", self.hwaccel, *self.device_args]


@dataclass(frozen=True)
class EncoderOption:
    """A video encoder with the arguments it needs around the filter graph."""

    name: str  # vendor-ish label
    codec: Codec
    encoder: str
    init_args: tuple[str, ...] = ()  # before the first -i (device setup)
    upload_filter: str | None = None  # appended last in the video chain (e.g. hwupload)
    quality_arg: str | None = None  # option taking a constant-quality value
    extra_args: tuple[str, ...] = ()

    @property
    def is_software(self) -> bool:
        return self.encoder in SOFTWARE_ENCODERS.values()

    def quality_args(self, quality: int) -> list[str]:
        """Encoder args for a constant quality (lower is better, CRF-like scale)."""
        if self.quality_arg is None:
            return list(self.extra_args)
        return [self.quality_arg, str(quality), *self.extra_args]


def _vaapi_device() -> str | None:
    nodes = sorted(glob.glob("/dev/dri/renderD*"))
    return nodes[0] if nodes else None


def decode_candidates(platform: str = sys.platform) -> list[DecodeOption]:
    """Decode candidates in preference order for the platform."""
    out = [
        DecodeOption("nvidia", "cuda"),
        DecodeOption("intel_qsv", "qsv"),
    ]
    if platform == "win32":
        out.append(DecodeOption("d3d11va", "d3d11va"))
    else:
        dev = _vaapi_device()
        out.append(DecodeOption("vaapi", "vaapi", ("-hwaccel_device", dev) if dev else ()))
    return out


def encoder_candidates(codec: Codec, platform: str = sys.platform) -> list[EncoderOption]:
    """Encoder candidates in preference order for the platform (software excluded)."""
    c = codec
    out = [
        EncoderOption("nvidia", c, f"{c}_nvenc", quality_arg="-cq", extra_args=("-preset", "p4")),
        EncoderOption("intel_qsv", c, f"{c}_qsv", quality_arg="-global_quality"),
    ]
    if platform == "win32":
        out.append(EncoderOption("amd_amf", c, f"{c}_amf", quality_arg="-qp_i"))
        if c == "h264":
            out.append(EncoderOption("media_foundation", c, f"{c}_mf", quality_arg="-q"))
    else:
        dev = _vaapi_device()
        if dev:
            out.append(
                EncoderOption(
                    "vaapi",
                    c,
                    f"{c}_vaapi",
                    init_args=("-vaapi_device", dev),
                    upload_filter="format=nv12,hwupload",
                    quality_arg="-qp",
                )
            )
    return out


def software_encoder(codec: Codec = "h264") -> EncoderOption:
    return EncoderOption("cpu", codec, SOFTWARE_ENCODERS[codec], quality_arg="-crf")


def _default_runner(args: list[str]) -> bool:
    return run_sync(args, timeout=15.0).returncode == 0


def _base(caps: FFmpegCaps) -> list[str]:
    return [str(caps.ffmpeg), "-hide_banner", "-v", "error", "-nostdin", "-y"]


def test_encode(caps: FFmpegCaps, option: EncoderOption, runner: Runner | None = None) -> bool:
    """Encode one synthetic frame with `option`; True when ffmpeg succeeds."""
    run = runner or _default_runner
    vf = ["-vf", f"format=yuv420p,{option.upload_filter}"] if option.upload_filter else []
    if not option.upload_filter and option.name != "cpu":
        vf = ["-vf", "format=nv12"]
    args = [
        *_base(caps), *option.init_args,
        "-f", "lavfi", "-i", f"testsrc2=s={TEST_SIZE}:r=25:d=0.2",
        "-frames:v", "1", *vf, "-c:v", option.encoder, "-f", "null", "-",
    ]  # fmt: skip
    return run(args)


def test_decode(
    caps: FFmpegCaps, option: DecodeOption, sample: Path, runner: Runner | None = None
) -> bool:
    """Decode one frame of `sample` (an H.264 file) with `option`."""
    run = runner or _default_runner
    args = [
        *_base(caps), *option.input_args(), "-i", str(sample),
        "-frames:v", "1", "-f", "null", "-",
    ]  # fmt: skip
    return run(args)


def _make_sample(caps: FFmpegCaps, directory: Path, runner: Runner | None) -> Path | None:
    sample = directory / "sample.mp4"
    args = [
        *_base(caps), "-f", "lavfi", "-i", f"testsrc2=s={TEST_SIZE}:r=25:d=0.2",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", str(sample),
    ]  # fmt: skip
    ok = (runner or _default_runner)(args)
    return sample if ok and (runner is not None or sample.exists()) else None


@dataclass(frozen=True)
class VideoHwReport:
    """Validated hardware paths, each list ordered best first."""

    decoders: list[DecodeOption] = field(default_factory=list)
    encoders: dict[Codec, list[EncoderOption]] = field(default_factory=dict)
    failed: list[str] = field(default_factory=list)  # candidates that listed but did not work

    def best_decoder(self) -> DecodeOption | None:
        return self.decoders[0] if self.decoders else None

    def to_dict(self) -> dict[str, object]:
        return {
            "decoders": [d.hwaccel for d in self.decoders],
            "encoders": {c: [e.encoder for e in v] for c, v in self.encoders.items()},
            "failed": self.failed,
        }


def probe_video_hw(
    caps: FFmpegCaps,
    *,
    codecs: tuple[Codec, ...] = ("h264", "hevc"),
    runner: Runner | None = None,
    platform: str = sys.platform,
) -> VideoHwReport:
    """Test every candidate that FFmpeg lists; keep those that really work."""
    failed: list[str] = []
    decoders: list[DecodeOption] = []
    with tempfile.TemporaryDirectory(prefix="vf-hw-") as tmp:
        sample = None
        listed = [d for d in decode_candidates(platform) if d.hwaccel in caps.hwaccels]
        if listed:
            sample = _make_sample(caps, Path(tmp), runner)
        for d in listed:
            if sample is not None and test_decode(caps, d, sample, runner):
                decoders.append(d)
            else:
                failed.append(f"decode:{d.hwaccel}")
    encoders: dict[Codec, list[EncoderOption]] = {}
    for codec in codecs:
        working: list[EncoderOption] = []
        for e in encoder_candidates(codec, platform):
            if e.encoder not in caps.encoders:
                continue
            if test_encode(caps, e, runner):
                working.append(e)
            else:
                failed.append(f"encode:{e.encoder}")
        encoders[codec] = working
    return VideoHwReport(decoders, encoders, failed)


def choose_encoder(
    report: VideoHwReport, codec: Codec = "h264", prefer: str = "auto"
) -> EncoderOption:
    """First working hardware encoder, else software. `prefer`: auto | cpu | <encoder name>."""
    if prefer != "cpu":
        for e in report.encoders.get(codec, []):
            if prefer in ("auto", e.encoder, e.name):
                return e
    return software_encoder(codec)


def choose_decoder(report: VideoHwReport, prefer: str = "auto") -> DecodeOption | None:
    """First working hardware decoder, or None (software decode)."""
    if prefer == "cpu":
        return None
    for d in report.decoders:
        if prefer in ("auto", d.hwaccel, d.name):
            return d
    return None
