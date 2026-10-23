from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from videoflow import samples


@pytest.fixture(scope="session")
def samples_dir() -> Path:
    """Synthetic rushes, generated once and cached by generator hash."""
    try:
        return samples.ensure_samples()
    except FileNotFoundError as exc:  # no ffmpeg/ffprobe available
        pytest.skip(str(exc))


@pytest.fixture(scope="session")
def samples_manifest(samples_dir: Path) -> dict[str, Any]:
    return json.loads((samples_dir / samples.MANIFEST_NAME).read_text(encoding="utf-8"))
