"""Project operations scoped to the application's project directory."""

import json
import re
import shutil
import uuid
from pathlib import Path

from videoflow.project.commands import RenameProject
from videoflow.project.models import new_project
from videoflow.project.store import Bundle


def project_name(name: str) -> str:
    name = name.strip()
    if not name or len(name) > 120 or any(ord(c) < 32 for c in name):
        raise ValueError("Use a project name of 1–120 characters")
    return name


class ProjectLibrary:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def entries(self) -> list[dict[str, str]]:
        entries = []
        for path in self.root.glob("*.videoflow"):
            if path.is_symlink() or path.resolve().parent != self.root:
                continue
            try:
                data = json.loads((path / "project.json").read_bytes())
                entries.append({"id": data["id"], "name": data["name"], "path": str(path)})
            except (OSError, ValueError, KeyError):
                continue
        return sorted(entries, key=lambda e: e["name"].casefold())

    def latest(self) -> Bundle | None:
        """The most recently saved project, opened at launch."""
        paths = [Path(e["path"]) for e in self.entries()]
        if not paths:
            return None
        bundle = Bundle(max(paths, key=lambda p: (p / "project.json").stat().st_mtime))
        bundle.load()
        return bundle

    def find(self, identifier: str) -> Bundle:
        entries = [e for e in self.entries() if e["id"] == identifier]
        if len(entries) != 1:
            raise ValueError("Unknown or ambiguous project")
        bundle = Bundle(entries[0]["path"])
        bundle.load()
        return bundle

    def folder(self, name: str, suffix: str | None = None) -> Path:
        """`<name>-<suffix>.videoflow`: readable, and unique through the suffix."""
        slug = re.sub(r"[^\w -]", "", project_name(name))[:60].strip() or "Project"
        return self.root / f"{slug}-{suffix or uuid.uuid4().hex[:12]}.videoflow"

    def create(self, name: str, source: Bundle | None = None) -> Bundle:
        name = project_name(name)
        path = self.folder(name)
        project = new_project(name)
        if source is not None:
            project = source.project.model_copy(
                deep=True,
                update={
                    "id": project.id,
                    "name": name,
                    "revision": 0,
                },
            )
            # Reference originals by their existing absolute paths, never duplicate media.
            for asset in project.assets:
                asset.rel_path = None
                if asset.model_extra:
                    asset.model_extra.pop("previewPath", None)
        target = Bundle.create(path, project)
        if source is not None:
            for folder in ("analysis", "features"):
                shutil.copytree(source.path / folder, target.path / folder, dirs_exist_ok=True)
        return target

    def rename(self, bundle: Bundle, name: str) -> Bundle:
        """Rename the project and its folder (keeping its unique suffix); returns the bundle.

        The caller must have closed everything that uses the bundle's files.
        """
        bundle.commit(bundle.project.revision, [RenameProject(name=project_name(name))])
        match = re.search(r"-([0-9a-f]{12})$", bundle.path.stem)
        target = self.folder(name, match.group(1) if match else None)
        if target == bundle.path or bundle.path.parent.resolve() != self.root:
            return bundle
        if target.exists():
            raise ValueError(f"A project folder named {target.name} already exists")
        try:
            bundle.path.rename(target)
        except PermissionError:
            return bundle  # a file is still in use (Windows): keep the folder, name is saved
        moved = Bundle(target)
        moved.load()
        return moved

    def delete(self, identifier: str) -> None:
        bundle = self.find(identifier)
        trash = self.root / ".trash"
        trash.mkdir(exist_ok=True)
        if trash.is_symlink() or trash.resolve().parent != self.root:
            raise ValueError("Invalid project trash directory")
        # Recoverable deletion: only this registered bundle moves, never its source files.
        bundle.path.rename(trash / f"{uuid.uuid4().hex}.videoflow")
