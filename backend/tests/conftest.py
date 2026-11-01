from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from videoflow import samples


@pytest.fixture(autouse=True, scope="session")
def _isolated_cache(tmp_path_factory: pytest.TempPathFactory) -> None:
    """Project caches go to a temporary root, never beside the repository."""
    import os

    os.environ["VIDEOFLOW_CACHE_DIR"] = str(tmp_path_factory.mktemp("cache"))


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
