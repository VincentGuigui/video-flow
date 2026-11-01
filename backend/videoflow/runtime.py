"""Application-owned files live beside the executable (or in the development root)."""

import os
import sys
from pathlib import Path


def application_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def assets_dir() -> Path:
    """Bundled resources (fonts, icons): `assets/` at the repository root, or in the build."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", application_dir())) / "assets"
    return application_dir() / "assets"


def recent_projects_file() -> Path:
    """The list of recently used projects (VIDEOFLOW_RECENT_PROJECTS overrides)."""
    override = os.environ.get("VIDEOFLOW_RECENT_PROJECTS")
    return Path(override) if override else application_dir() / "recent-projects.json"


def cache_root() -> Path:
    """Rebuildable per-project caches: `cache/<project id>/` beside the executable.

    VIDEOFLOW_CACHE_DIR overrides it (tests, or another drive with more space).
    """
    override = os.environ.get("VIDEOFLOW_CACHE_DIR")
    return Path(override) if override else application_dir() / "cache"


def model_directory() -> Path:
    path = application_dir() / "models"
    os.environ["VIDEOFLOW_MODELS_DIR"] = str(path)
    # Keep library-owned auxiliary files in the same application subtree too.
    os.environ["HF_HOME"] = str(path / "huggingface")
    os.environ["HF_HUB_CACHE"] = str(path / "hf")
    os.environ["HF_XET_CACHE"] = str(path / "xet")
    return path


def open_folder(path: Path) -> None:
    """Show a folder in the system file manager (Windows Explorer or the Linux default)."""
    path.mkdir(parents=True, exist_ok=True)
    if sys.platform == "win32":
        os.startfile(path)  # type: ignore[attr-defined]  # noqa: S606
    else:
        import subprocess

        opener = "open" if sys.platform == "darwin" else "xdg-open"
        subprocess.Popen([opener, str(path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
