"""Single-use native selections. A handle confers access to one selected file or folder."""

import secrets
import time
from dataclasses import dataclass
from pathlib import Path

from videoflow.media.ingest import MEDIA_EXTENSIONS
from videoflow.project.library import is_project


@dataclass(frozen=True)
class Grant:
    path: Path
    asset_id: str | None
    expires: float
    purpose: str = "media"
    """"media" (a file), "workdir" (a working folder) or "project" (a project folder)."""


class SelectionGrants:
    def __init__(self) -> None:
        self._grants: dict[str, Grant] = {}

    def issue(self, paths: list[Path], asset_id: str | None = None) -> list[dict[str, str]]:
        now = time.monotonic()
        self._grants = {key: grant for key, grant in self._grants.items() if grant.expires > now}
        result = []
        for path in paths:
            canonical = path.resolve(strict=True)
            if not canonical.is_file() or canonical.suffix.casefold() not in MEDIA_EXTENSIONS:
                raise ValueError(f"Not a supported local media file: {path.name}")
            handle = secrets.token_urlsafe(32)
            self._grants[handle] = Grant(canonical, asset_id, now + 3600)
            result.append({"handle": handle, "name": canonical.name})
        return result

    def issue_folder(self, path: Path, purpose: str) -> dict[str, str]:
        """A handle for a working folder, or for a project folder (holding project.json)."""
        canonical = path.resolve(strict=True)
        if purpose not in ("workdir", "project") or not canonical.is_dir():
            raise ValueError(f"Not a folder: {path.name}")
        if purpose == "project" and not is_project(canonical):
            raise ValueError(
                f"{canonical.name} is not a Video-Flow project: choose a <name>.video-flow"
                " folder that contains project.json"
            )
        handle = secrets.token_urlsafe(32)
        self._grants[handle] = Grant(canonical, None, time.monotonic() + 3600, purpose)
        return {"handle": handle, "name": canonical.name, "path": str(canonical)}

    def consume_folder(self, handle: str, purpose: str) -> Path:
        grant = self._grants.get(handle)
        if grant is None or grant.expires < time.monotonic() or grant.purpose != purpose:
            raise ValueError("Folder selection is invalid, expired or for another operation")
        del self._grants[handle]
        if not grant.path.is_dir():
            raise ValueError("Selected folder is no longer available")
        return grant.path

    def consume(self, handle: str, *, asset_id: str | None = None) -> Path:
        grant = self._grants.get(handle)
        if (
            grant is None
            or grant.expires < time.monotonic()
            or grant.asset_id != asset_id
            or grant.purpose != "media"
        ):
            raise ValueError("Native file selection is invalid, expired or for another operation")
        del self._grants[handle]
        if not grant.path.is_file():
            raise ValueError("Selected media is no longer available")
        return grant.path
