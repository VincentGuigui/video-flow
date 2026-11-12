"""Video rules shared by the preview media (`editor/previews.py`): size, CFR rate, 8-bit SDR
BT.709 filter chain with rotation baked in and HDR tone mapping; and the still-image preview.

Preview time equals source time (no offset): the fps filter only snaps frames to the grid
and audio keeps its start.
"""

from __future__ import annotations

import os
from fractions import Fraction
from pathlib import Path

from videoflow.hw.video import VideoHwReport, probe_video_hw
from videoflow.media import ffmpeg
from videoflow.media.caps import FFmpegCaps, get_caps
from videoflow.media.errors import MediaError
from videoflow.media.ffmpeg import VideoStreamInfo
from videoflow.media.hashing import cache_key

DEFAULT_HEIGHT = 540
MAX_FPS = 60
DEFAULT_FPS = Fraction(30)

COLOR_TAGS = [
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


STILL_PREVIEW_VERSION = 1
STILL_PREVIEW_MAX = 1920
"""Longest side of the preview picture of a still image
(docs/features/import-analysis/still-images.md)."""


async def build_still_preview(
    src: Path | str, out_dir: Path | str, content_hash: str, *, caps: FFmpegCaps | None = None
) -> Path:
    """Build (or reuse) a PNG of a still image fitting STILL_PREVIEW_MAX, alpha kept.

    The preview shows it in place of a video proxy; formats browsers cannot show (TIFF)
    and very large photos are converted once.
    """
    caps = caps or get_caps()
    out_dir = Path(out_dir)
    out = (
        out_dir
        / f"{cache_key(content_hash, 'still', STILL_PREVIEW_VERSION, STILL_PREVIEW_MAX)}.png"
    )
    if out.is_file():
        return out
    out_dir.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(out.stem + ".part.png")
    side = STILL_PREVIEW_MAX
    res = await ffmpeg.run(
        [
            "-y", "-i", str(src), "-frames:v", "1",
            "-vf", f"scale='min({side},iw)':'min({side},ih)':force_original_aspect_ratio=decrease",
            "-update", "1", str(tmp),
        ],
        ffmpeg=caps.ffmpeg,
    )  # fmt: skip
    if not res.ok or not tmp.is_file():
        tmp.unlink(missing_ok=True)
        raise MediaError(f"still preview failed for {src}", res.stderr_tail)
    os.replace(tmp, out)
    return out
