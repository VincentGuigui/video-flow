"""The application cache: one rebuildable folder per project under runtime.cache_root()."""

import shutil
from pathlib import Path


def folder_size(path: Path) -> int:
    total = 0
    for item in path.rglob("*"):
        try:
            if item.is_file() and not item.is_symlink():
                total += item.stat().st_size
        except OSError:
            continue
    return total


def usage(root: Path) -> list[dict[str, object]]:
    """Every project cache with its size and the project it belongs to (if known)."""
    entries: list[dict[str, object]] = []
    if not root.is_dir():
        return entries
    for folder in sorted(p for p in root.iterdir() if p.is_dir() and not p.is_symlink()):
        name, path = folder.name, ""
        label = folder / "project.txt"
        if label.is_file():
            lines = label.read_text(encoding="utf-8").splitlines()
            name, path = (lines + ["", ""])[0] or folder.name, (lines + ["", ""])[1]
        entries.append({"id": folder.name, "name": name, "path": path, "size": folder_size(folder)})
    return entries


def clear(root: Path) -> list[str]:
    """Delete every project cache; returns the folders that could not be fully removed."""
    failed = []
    if root.is_dir():
        for folder in root.iterdir():
            if folder.is_dir() and not folder.is_symlink():
                shutil.rmtree(folder, ignore_errors=True)
                if folder.exists():
                    failed.append(folder.name)
    return failed
