from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from videoflow.media.caps import locate_binaries


def run_ffprobe(*args: str) -> str:
    exe = str(locate_binaries().ffprobe)
    return subprocess.run(
        [exe, "-v", "error", *args], capture_output=True, text=True, check=True
    ).stdout


@pytest.fixture(scope="session")
def rotated_clip(tmp_path_factory: pytest.TempPathFactory, samples_dir: Path) -> Path:
    """Landscape clip carrying a 90 degree display matrix (a phone held upright)."""
    out = tmp_path_factory.mktemp("rot") / "rotated.mp4"
    subprocess.run(
        [str(locate_binaries().ffmpeg), "-v", "error", "-y", "-display_rotation", "90",
         "-i", str(samples_dir / "clip_silent.mp4"), "-c", "copy", str(out)],
        check=True,
    )  # fmt: skip
    return out
