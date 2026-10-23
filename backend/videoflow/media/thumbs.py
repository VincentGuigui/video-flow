"""Thumbnail sprites: one frame per 2 s, 160 px wide, tiled into JPEG sheets plus an index."""

from __future__ import annotations

import asyncio
import json
import math
import shutil
from dataclasses import dataclass
from pathlib import Path

from videoflow.media import ffmpeg
from videoflow.media.caps import FFmpegCaps, get_caps
from videoflow.media.errors import MediaCancelled, MediaError
from videoflow.media.hashing import cache_key

THUMBS_VERSION = 1
INTERVAL_S = 2
THUMB_WIDTH = 160
COLS = 10
ROWS = 10
INDEX_NAME = "index.json"


@dataclass(frozen=True)
class ThumbsResult:
    directory: Path
    cached: bool
    index: dict[str, object]

    @property
    def index_path(self) -> Path:
        return self.directory / INDEX_NAME


def thumb_height(display_w: int, display_h: int, width: int = THUMB_WIDTH) -> int:
    return max(2, int(round(width * display_h / display_w / 2)) * 2)


def thumb_count(duration_us: int, interval_s: int = INTERVAL_S) -> int:
    return max(1, math.ceil(duration_us / (interval_s * 1_000_000)))


async def build_thumbs(
    src: Path | str,
    out_dir: Path | str,
    content_hash: str,
    *,
    display_size: tuple[int, int],
    duration_us: int,
    caps: FFmpegCaps | None = None,
    cancel: asyncio.Event | None = None,
    force: bool = False,
) -> ThumbsResult:
    """Sprite sheets of `src` (best the proxy: already upright, SDR and cheap to decode).

    Output dir `<out_dir>/<key>/` holds `sheet_000.jpg`... and `index.json`: thumbnail `i` is
    at `i * intervalUs`, in sheet `i // perSheet`, cell `(i % perSheet) % cols`, `// cols`.
    """
    caps = caps or get_caps()
    final = Path(out_dir) / cache_key(content_hash, "thumbs", THUMBS_VERSION)
    if (final / INDEX_NAME).is_file() and not force:
        return ThumbsResult(final, True, json.loads((final / INDEX_NAME).read_text("utf-8")))
    th = thumb_height(*display_size)
    count = thumb_count(duration_us)
    per_sheet = COLS * ROWS
    tmp = final.with_name(final.name + ".part")
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    args = [
        "-nostdin", "-y", "-i", str(src), "-an", "-sn",
        "-vf", f"fps=1/{INTERVAL_S}:round=down,scale={THUMB_WIDTH}:{th},tile={COLS}x{ROWS}",
        "-frames:v", str(math.ceil(count / per_sheet)), "-fps_mode", "passthrough",
        "-q:v", "6", "-pix_fmt", "yuvj420p", str(tmp / "sheet_%03d.jpg"),
    ]  # fmt: skip
    res = await ffmpeg.run(args, cancel=cancel, ffmpeg=caps.ffmpeg)
    if res.cancelled:
        shutil.rmtree(tmp, ignore_errors=True)
        raise MediaCancelled("thumbnails cancelled")
    sheets = sorted(p.name for p in tmp.glob("sheet_*.jpg"))
    if not res.ok or not sheets:
        shutil.rmtree(tmp, ignore_errors=True)
        raise MediaError(f"thumbnail extraction failed for {src}", res.stderr_tail)
    index: dict[str, object] = {
        "version": THUMBS_VERSION,
        "intervalUs": INTERVAL_S * 1_000_000,
        "thumbWidth": THUMB_WIDTH,
        "thumbHeight": th,
        "cols": COLS,
        "rows": ROWS,
        "perSheet": per_sheet,
        "count": count,
        "sheets": sheets,
    }
    (tmp / INDEX_NAME).write_text(json.dumps(index, indent=2), encoding="utf-8")
    shutil.rmtree(final, ignore_errors=True)
    tmp.rename(final)
    return ThumbsResult(final, False, index)
