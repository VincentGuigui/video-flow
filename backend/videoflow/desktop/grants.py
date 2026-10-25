"""Single-use native selections. Handles confer access to one selected file only."""

import secrets
import time
from dataclasses import dataclass
from pathlib import Path

from videoflow.media.ingest import MEDIA_EXTENSIONS


@dataclass(frozen=True)
class Grant:
    path: Path
    asset_id: str | None
    expires: float


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

    def consume(self, handle: str, *, asset_id: str | None = None) -> Path:
        grant = self._grants.get(handle)
        if grant is None or grant.expires < time.monotonic() or grant.asset_id != asset_id:
            raise ValueError("Native file selection is invalid, expired or for another operation")
        del self._grants[handle]
        if not grant.path.is_file():
            raise ValueError("Selected media is no longer available")
        return grant.path
