from __future__ import annotations

import subprocess
from pathlib import Path

import numpy as np
import pytest

from videoflow.media.caps import locate_binaries


def decode_audio(path: Path, sample_rate: int = 16_000, seconds: float | None = None) -> np.ndarray:
    """Mono float32 samples of the first audio stream at ``sample_rate``."""
    cmd = [str(locate_binaries().ffmpeg), "-v", "error", "-nostdin", "-i", str(path)]
    if seconds is not None:
        cmd += ["-t", str(seconds)]
    cmd += ["-vn", "-ac", "1", "-ar", str(sample_rate), "-f", "f32le", "-"]
    raw = subprocess.run(cmd, capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype="<f4").copy()


@pytest.fixture(scope="session")
def audio_loader():
    return decode_audio
