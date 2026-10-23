"""Decode sampled RGB frames from a video with FFmpeg (rawvideo pipe, no shell)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import numpy as np

from videoflow.engines.protocols import FrameArray
from videoflow.media.caps import locate_binaries

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def sample_frames(
    video_path: Path, *, fps: float = 2.0, width: int = 320, height: int = 180
) -> list[FrameArray]:
    """Frames at ``fps`` scaled to ``width`` x ``height`` (RGB uint8, ``(h, w, 3)``)."""
    cmd = [
        str(locate_binaries().ffmpeg), "-v", "error", "-nostdin", "-i", str(video_path),
        "-vf", f"fps={fps},scale={width}:{height}", "-pix_fmt", "rgb24", "-f", "rawvideo", "-",
    ]  # fmt: skip
    raw = subprocess.run(cmd, capture_output=True, check=True, creationflags=_NO_WINDOW).stdout
    size = width * height * 3
    count = len(raw) // size
    arr = np.frombuffer(raw[: count * size], dtype=np.uint8).reshape(count, height, width, 3)
    return [f.copy() for f in arr]
