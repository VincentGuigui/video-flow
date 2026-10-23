"""Proxy video: H.264 8-bit SDR BT.709, CFR, keyframe every second, rotation baked in.

Proxy time equals source time (no offset): the fps filter only snaps frames to the grid and
audio keeps its start. Hardware decode and encode come from `videoflow.hw.video`, with a
libx264 / software-decode retry when the hardware path fails at run time.
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

from videoflow.hw.video import (
    DecodeOption,
    EncoderOption,
    VideoHwReport,
    choose_decoder,
    choose_encoder,
    probe_video_hw,
    software_encoder,
)
from videoflow.media import ffmpeg
from videoflow.media.caps import FFmpegCaps, get_caps
from videoflow.media.errors import MediaCancelled, MediaError
from videoflow.media.ffmpeg import ProbeResult, ProgressCallback, VideoStreamInfo
from videoflow.media.hashing import cache_key

PROXY_VERSION = 1
DEFAULT_HEIGHT = 540
KEYFRAME_INTERVAL_S = 1
MAX_FPS = 60
DEFAULT_FPS = Fraction(30)
CRF = 23
DURATION_TOLERANCE_US = 100_000

_TAG_ARGS = [
    "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
    "-color_range", "tv",
]  # fmt: skip
_HDR_IN = {  # color_transfer -> zscale input transfer name
    "arib-std-b67": "arib-std-b67",
    "smpte2084": "smpte2084",
}
_hw_reports: dict[Path, VideoHwReport] = {}


def default_hw_report(caps: FFmpegCaps) -> VideoHwReport:
    """Process-wide cached hardware probe (one-frame test runs) for this FFmpeg build."""
    if caps.ffmpeg not in _hw_reports:
        _hw_reports[caps.ffmpeg] = probe_video_hw(caps, codecs=("h264",))
    return _hw_reports[caps.ffmpeg]


@dataclass(frozen=True)
class ProxyResult:
    path: Path
    cached: bool
    width: int
    height: int
    fps: Fraction
    encoder: str
    hwaccel: str | None
    tone_mapped: bool
    duration_delta_us: int | None = None
    """Proxy minus source duration; large values mean proxy time drifted from source time."""

    @property
    def time_aligned(self) -> bool:
        return (
            self.duration_delta_us is None or abs(self.duration_delta_us) <= DURATION_TOLERANCE_US
        )


def proxy_size(display_w: int, display_h: int, target: int = DEFAULT_HEIGHT) -> tuple[int, int]:
    """Even output size whose short side is at most `target` (never upscaled)."""
    short = min(display_w, display_h)
    ratio = min(1.0, target / short)

    def even(v: float) -> int:
        return max(2, int(round(v / 2)) * 2)

    return even(display_w * ratio), even(display_h * ratio)


def proxy_fps(v: VideoStreamInfo) -> Fraction:
    """CFR rate: the container rate for VFR media, the stream rate otherwise; capped at 60."""
    rate = v.r_fps if v.is_vfr and v.r_fps > 0 else v.fps
    if rate <= 0:
        return DEFAULT_FPS
    while rate > MAX_FPS:
        rate /= 2
    return rate.limit_denominator(1001)


def _tone_map_chain(v: VideoStreamInfo) -> str:
    tin = _HDR_IN.get(v.color_transfer or "", "arib-std-b67")
    return (
        f"zscale=tin={tin}:pin=bt2020:min=bt2020nc:rin=tv:t=linear:npl=100,"
        "format=gbrpf32le,zscale=p=bt709,tonemap=tonemap=hable:desat=0,"
        "zscale=t=bt709:m=bt709:r=tv"
    )


def video_filter(
    v: VideoStreamInfo, size: tuple[int, int], fps: Fraction, caps: FFmpegCaps
) -> tuple[str, bool]:
    """Filter chain (without hardware upload) and whether HDR tone mapping is applied."""
    w, h = size
    parts: list[str] = []
    tone = v.is_hdr and caps.has_filter("zscale") and caps.has_filter("tonemap")
    if tone:
        parts.append(_tone_map_chain(v))
    scale = f"scale={w}:{h}:flags=bicubic:out_color_matrix=bt709:out_range=tv"
    if not v.is_hdr and v.color_space in (None, "unknown", "unspecified"):
        scale += ":in_color_matrix=" + ("bt709" if v.height >= 720 else "bt601")
    parts += [scale, f"fps={fps.numerator}/{fps.denominator}:round=near", "setsar=1"]
    parts.append("format=yuv420p")
    return ",".join(parts), tone


def build_args(
    src: Path,
    out: Path,
    probe: ProbeResult,
    *,
    caps: FFmpegCaps,
    encoder: EncoderOption,
    decoder: DecodeOption | None,
    height: int = DEFAULT_HEIGHT,
) -> tuple[list[str], tuple[int, int], Fraction, bool]:
    v = probe.video
    assert v is not None
    size = proxy_size(*v.display_size, target=height)
    fps = proxy_fps(v)
    vf, tone = video_filter(v, size, fps, caps)
    if encoder.upload_filter:
        vf += "," + encoder.upload_filter
    gop = max(1, round(float(fps) * KEYFRAME_INTERVAL_S))
    args = [
        "-nostdin", "-y", *encoder.init_args,
        *(decoder.input_args() if decoder else []),
        "-i", str(src),
        "-map", "0:v:0", "-map", "0:a:0?", "-sn", "-dn", "-map_metadata", "-1",
        "-vf", vf, "-fps_mode", "cfr",
        "-c:v", encoder.encoder, *encoder.quality_args(CRF),
        "-g", str(gop), "-force_key_frames", f"expr:gte(t,n_forced*{KEYFRAME_INTERVAL_S})",
        *_TAG_ARGS,
    ]  # fmt: skip
    if encoder.is_software:
        args += ["-preset", "veryfast", "-profile:v", "high", "-sc_threshold", "0",
                 "-bf", "2"]  # fmt: skip
    args += [
        "-c:a", "aac", "-ac", "2", "-ar", "48000", "-b:a", "128k",
        "-movflags", "+faststart", "-f", "mp4", str(out),
    ]  # fmt: skip
    return args, size, fps, tone


async def build_proxy(
    src: Path | str,
    out_dir: Path | str,
    content_hash: str,
    *,
    probe: ProbeResult | None = None,
    height: int = DEFAULT_HEIGHT,
    hw: str = "auto",
    hw_report: VideoHwReport | None = None,
    caps: FFmpegCaps | None = None,
    on_progress: ProgressCallback | None = None,
    cancel: asyncio.Event | None = None,
    force: bool = False,
) -> ProxyResult | None:
    """Build (or reuse) the proxy of `src`; None for media without video.

    `hw`: auto | cpu | an encoder or vendor name from `hw.video`.
    """
    src = Path(src)
    pr = probe or await ffmpeg.probe(src)
    v = pr.video
    if v is None:
        return None
    caps = caps or get_caps()
    out_dir = Path(out_dir)
    out = out_dir / f"{cache_key(content_hash, 'proxy', PROXY_VERSION, height)}.mp4"
    size = proxy_size(*v.display_size, target=height)
    fps = proxy_fps(v)
    tone = v.is_hdr and caps.has_filter("zscale") and caps.has_filter("tonemap")
    if out.is_file() and not force:
        return ProxyResult(out, True, *size, fps, "cached", None, tone)
    out_dir.mkdir(parents=True, exist_ok=True)

    attempts: list[tuple[EncoderOption, DecodeOption | None]] = []
    if hw != "cpu":
        report = hw_report
        if report is None:
            report = await asyncio.to_thread(default_hw_report, caps)
        enc = choose_encoder(report, "h264", hw)
        dec = choose_decoder(report, hw)
        if not enc.is_software or dec is not None:
            attempts.append((enc, dec))
    attempts.append((software_encoder("h264"), None))

    tmp = out.with_name(out.stem + ".part.mp4")
    last_err = ""
    for enc, dec in attempts:
        args, size, fps, tone = build_args(
            src, tmp, pr, caps=caps, encoder=enc, decoder=dec, height=height
        )
        res = await ffmpeg.run(
            args, on_progress=on_progress, cancel=cancel, duration_us=pr.duration_us,
            ffmpeg=caps.ffmpeg,
        )  # fmt: skip
        if res.cancelled:
            tmp.unlink(missing_ok=True)
            raise MediaCancelled("proxy cancelled")
        if res.ok and tmp.is_file():
            os.replace(tmp, out)
            delta = None
            if pr.duration_us is not None:
                out_pr = await ffmpeg.probe(out)
                if out_pr.duration_us is not None:
                    delta = out_pr.duration_us - pr.duration_us
            return ProxyResult(
                out, False, *size, fps, enc.encoder, dec.hwaccel if dec else None, tone, delta
            )
        last_err = res.stderr_tail
        tmp.unlink(missing_ok=True)
    raise MediaError(f"proxy encode failed for {src}", last_err)
