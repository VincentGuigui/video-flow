"""Projects in working folders, and the list of recently used projects.

A project is a `<name>.video-flow` folder inside the user's working folder, next to (or
above) the original media it references with relative paths. Copying the working
folder copies a working project. The application keeps only a list of recent
projects (`recent-projects.json` beside the executable); projects live where the user
put them.
"""

import contextlib
import json
import os
import re
import shutil
from pathlib import Path

from videoflow.project.commands import RenameProject
from videoflow.project.models import new_project
from videoflow.project.store import Bundle

SUFFIX = ".video-flow"
LEGACY_SUFFIX = ".videoflow"
MAX_RECENT = 20


def project_name(name: str) -> str:
    name = name.strip()
    if not name or len(name) > 120 or any(ord(c) < 32 for c in name):
        raise ValueError("Use a project name of 1–120 characters")
    return name


def folder_name(name: str) -> str:
    """A file-system safe `<name>.video-flow` on Windows and Linux."""
    safe = re.sub(r'[<>:"/\\|?*]', "", project_name(name)).strip(" .")[:80] or "Project"
    return safe + SUFFIX


def is_project(path: Path) -> bool:
    """A project folder: named `*.video-flow` (or `*.videoflow` before 0.2) with project.json."""
    return path.suffix.casefold() in (SUFFIX, LEGACY_SUFFIX) and (path / "project.json").is_file()


def open_bundle(path: Path) -> Bundle:
    if not is_project(path):
        raise ValueError(
            f"{path.name} is not a Video-Flow project: choose a <name>.video-flow folder"
            " that contains project.json"
        )
    bundle = Bundle(path.resolve())
    bundle.load()
    return bundle


class ProjectLibrary:
    def __init__(self, recent_file: Path) -> None:
        self.recent_file = recent_file

    # -- recent list -------------------------------------------------------------

    def _paths(self) -> list[Path]:
        try:
            data = json.loads(self.recent_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        return [Path(p) for p in data if isinstance(p, str)] if isinstance(data, list) else []

    def _write(self, paths: list[Path]) -> None:
        unique = list(dict.fromkeys(str(p) for p in paths))[:MAX_RECENT]
        with contextlib.suppress(OSError):
            self.recent_file.parent.mkdir(parents=True, exist_ok=True)
            self.recent_file.write_text(json.dumps(unique, indent=2), encoding="utf-8")

    def add(self, bundle: Bundle) -> None:
        """Put a project first in the recent list."""
        path = bundle.path.resolve()
        self._write([path, *[p for p in self._paths() if p != path]])

    def remove(self, identifier: str) -> None:
        """Forget a project; its folder is left untouched."""
        keep = [Path(e["path"]) for e in self.entries() if e["id"] != identifier]
        self._write(keep)

    def entries(self) -> list[dict[str, str]]:
        """Recent projects that still exist, most recent first."""
        entries = []
        for path in self._paths():
            try:
                data = json.loads((path / "project.json").read_bytes())
                entries.append(
                    {
                        "id": data["id"],
                        "name": data["name"],
                        "path": str(path),
                        "folder": str(path.parent),
                    }
                )
            except (OSError, ValueError, KeyError):
                continue
        return entries

    def latest(self) -> Bundle | None:
        """The most recently used project, opened at launch."""
        for entry in self.entries():
            with contextlib.suppress(OSError, ValueError):
                return open_bundle(Path(entry["path"]))
        return None

    def find(self, identifier: str) -> Bundle:
        entries = [e for e in self.entries() if e["id"] == identifier]
        if len(entries) != 1:
            raise ValueError("Unknown or ambiguous project")
        return open_bundle(Path(entries[0]["path"]))

    # -- projects ----------------------------------------------------------------

    def create(self, folder: Path, name: str, source: Bundle | None = None) -> Bundle:
        """A new project (or a copy of `source`) as `<folder>/<name>.video-flow`."""
        name = project_name(name)
        if not folder.is_dir():
            raise ValueError(f"Working folder not found: {folder}")
        path = folder.resolve() / folder_name(name)
        if path.exists():
            raise ValueError(f"{path.name} already exists in {folder}")
        project = new_project(name)
        if source is not None:
            project = source.project.model_copy(
                deep=True, update={"id": project.id, "name": name, "revision": 0}
            )
            base = path.parent
            for asset in project.assets:
                # Media keep working from the new folder through their relative paths.
                with contextlib.suppress(ValueError):
                    asset.rel_path = Path(os.path.relpath(asset.path, base)).as_posix()
                if asset.model_extra:
                    asset.model_extra.pop("previewPath", None)
        target = Bundle.create(path, project)
        if source is not None:
            for sub in ("analysis", "features"):
                if (source.path / sub).is_dir():
                    shutil.copytree(source.path / sub, target.path / sub, dirs_exist_ok=True)
        self.add(target)
        return target

    def rename(self, bundle: Bundle, name: str) -> Bundle:
        """Rename the project and its folder (`<name>.video-flow`); returns the bundle.

        The caller must have closed everything that uses the bundle's files.
        """
        bundle.commit(bundle.project.revision, [RenameProject(name=project_name(name))])
        target = bundle.path.parent / folder_name(name)
        if target == bundle.path:
            return bundle
        if target.exists():
            raise ValueError(f"{target.name} already exists in {target.parent}")
        old = bundle.path.resolve()
        try:
            bundle.path.rename(target)
        except PermissionError:
            return bundle  # a file is still in use (Windows): keep the folder, name is saved
        self._write([target.resolve() if p == old else p for p in self._paths()])
        return open_bundle(target)
