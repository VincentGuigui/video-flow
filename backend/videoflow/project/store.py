"""Project bundle on disk: layout, atomic save, migrations, history log, revisions.

Layout of ``<name>.videoflow/`` (05 §2 as corrected by 08 §3)::

    project.json        decisions (source of truth, schema-versioned)
    project.v<N>.bak.json  original file kept before a migration
    timeline.otio       compiled current cut (regenerated, debounced)
    history.jsonl       append-only command log: write-ahead and audit, not the undo engine
    analysis/           derived JSON per stage (rebuildable)
    features/           embeddings .npy, peaks .bin (rebuildable)
    cache/{proxies,thumbs,previews}/
    exports/  renders/

Writes go through :func:`save_atomic` (temp file in the same folder, fsync, rename), so a
crash leaves either the old or the new ``project.json``, never a torn one. A history line
is appended (and fsynced) *before* ``project.json`` is replaced; on load, lines newer
than the saved revision are replayed.
"""

import contextlib
import json
import os
import shutil
import threading
import time
import uuid
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import Field, ValidationError

from videoflow import __version__
from videoflow.core.base import CamelModel
from videoflow.project.commands import Command, CommandError, apply_batch
from videoflow.project.migrations import MIGRATIONS, Migration, can_write, migrate, schema_version
from videoflow.project.models import SCHEMA_VERSION, Project

BUNDLE_SUFFIX = ".videoflow"
_REPLACE_RETRIES = 10


class ProjectStoreError(Exception):
    pass


class ReadOnlyProjectError(ProjectStoreError):
    """The file needs a newer app to be written (``app.minReader`` too high)."""


class StaleRevisionError(ProjectStoreError):
    def __init__(self, base_revision: int, current_revision: int) -> None:
        super().__init__(f"stale base revision {base_revision} (current {current_revision})")
        self.base_revision = base_revision
        self.current_revision = current_revision


class HistoryEntry(CamelModel):
    """One line of ``history.jsonl``: a committed command batch."""

    schema_version: int = SCHEMA_VERSION
    revision: int
    """Revision produced by this batch."""
    base_revision: int
    at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat(timespec="milliseconds"))
    commands: list[Command]
    inverses: list[Command]


def save_atomic(
    path: Path, data: bytes, *, before_replace: Callable[[Path], None] | None = None
) -> None:
    """Write ``data`` to ``path`` atomically (same-folder temp file, fsync, rename).

    ``before_replace`` is a test hook called with the temp path just before the rename.
    """
    path = Path(path)
    tmp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with open(tmp, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        if before_replace is not None:
            before_replace(tmp)
        _replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    _fsync_dir(path.parent)


def _replace(src: Path, dst: Path) -> None:
    # On Windows a reader or an antivirus can hold the target open for a moment.
    for attempt in range(_REPLACE_RETRIES):
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            if os.name != "nt" or attempt == _REPLACE_RETRIES - 1:
                raise
            time.sleep(0.05 * (attempt + 1))


def _fsync_dir(folder: Path) -> None:
    if os.name == "nt":  # directories cannot be opened for fsync on Windows
        return
    try:
        fd = os.open(folder, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def dumps_project(project: Project) -> bytes:
    """`project.json` bytes, stamped with the application version that writes them."""
    project.app.writer = f"videoflow {__version__}"
    project.app.version = __version__
    text = json.dumps(project.dump(), indent=2, ensure_ascii=False) + "\n"
    return text.encode("utf-8")


class Bundle:
    """A ``.videoflow`` project folder. Thread-safe for one process."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.read_only = False
        self.migrated_from: list[int] = []
        self._project: Project | None = None
        self._lock = threading.RLock()

    # -- layout ----------------------------------------------------------------

    @property
    def project_file(self) -> Path:
        return self.path / "project.json"

    @property
    def timeline_file(self) -> Path:
        return self.path / "timeline.otio"

    @property
    def history_file(self) -> Path:
        return self.path / "history.jsonl"

    @property
    def analysis_dir(self) -> Path:
        return self.path / "analysis"

    @property
    def features_dir(self) -> Path:
        return self.path / "features"

    @property
    def cache_dir(self) -> Path:
        """Rebuildable data, outside the project so copying a working folder stays light."""
        from videoflow.runtime import cache_root

        return cache_root() / self.project.id

    @property
    def proxies_dir(self) -> Path:
        return self.cache_dir / "proxies"

    @property
    def thumbs_dir(self) -> Path:
        return self.cache_dir / "thumbs"

    @property
    def previews_dir(self) -> Path:
        return self.cache_dir / "previews"

    @property
    def exports_dir(self) -> Path:
        return self.path / "exports"

    @property
    def renders_dir(self) -> Path:
        return self.path / "renders"

    def backup_file(self, version: int) -> Path:
        return self.path / f"project.v{version}.bak.json"

    def directories(self) -> list[Path]:
        return [
            self.analysis_dir,
            self.features_dir,
            self.proxies_dir,
            self.thumbs_dir,
            self.previews_dir,
            self.exports_dir,
            self.renders_dir,
        ]

    def exists(self) -> bool:
        return self.project_file.is_file()

    # -- lifecycle -------------------------------------------------------------

    @classmethod
    def create(cls, path: Path | str, project: Project) -> "Bundle":
        bundle = cls(path)
        if bundle.exists():
            raise ProjectStoreError(f"a project already exists at {bundle.path}")
        bundle.path.mkdir(parents=True, exist_ok=True)
        bundle._project = project
        for folder in bundle.directories():
            folder.mkdir(parents=True, exist_ok=True)
        bundle.save(project)
        bundle.label_cache()
        return bundle

    def label_cache(self) -> None:
        """Name the cache folder after its project, for the cache list in Settings."""
        label = self.cache_dir / "project.txt"
        text = f"{self.project.name}\n{self.path.resolve()}\n"
        with contextlib.suppress(OSError):
            if not label.is_file() or label.read_text(encoding="utf-8") != text:
                label.parent.mkdir(parents=True, exist_ok=True)
                label.write_text(text, encoding="utf-8")

    def load(
        self,
        *,
        migrations: Mapping[int, Migration] = MIGRATIONS,
        target_version: int = SCHEMA_VERSION,
    ) -> Project:
        """Read, migrate (keeping a ``.bak`` of the original), validate and replay history."""
        with self._lock:
            self._remove_stale_temp_files()
            raw_bytes = self.project_file.read_bytes()
            try:
                data = json.loads(raw_bytes)
            except json.JSONDecodeError as exc:
                raise ProjectStoreError(f"{self.project_file} is not valid JSON: {exc}") from exc
            if not isinstance(data, dict):
                raise ProjectStoreError(f"{self.project_file} must hold a JSON object")
            original_version = schema_version(data)
            migrated, applied = migrate(data, target=target_version, migrations=migrations)
            try:
                project = Project.model_validate(migrated)
            except ValidationError as exc:
                raise ProjectStoreError(f"invalid project file: {exc}") from exc
            self.read_only = not can_write(migrated)
            self.migrated_from = applied
            if applied:
                backup = self.backup_file(original_version)
                if not backup.exists():
                    save_atomic(backup, raw_bytes)
            project = self._replay_history(project)
            self._resolve_media(project)
            self._project = project
            self.label_cache()
            self._remove_legacy_cache()
            older_app = project.app.version != __version__
            if (
                applied or older_app or project.revision != data.get("revision")
            ) and not self.read_only:
                # Opened fine (migrated if needed): from now on it is a current-version file.
                save_atomic(self.project_file, dumps_project(project))
            return project

    def _remove_legacy_cache(self) -> None:
        """Projects before 0.2 kept rebuildable caches in `<project>/cache/`: remove it."""
        from videoflow.runtime import cache_root

        legacy = self.path / "cache"
        if self.read_only or not legacy.is_dir() or legacy.is_symlink():
            return
        if cache_root().resolve().is_relative_to(legacy.resolve()):
            return  # never the application cache itself
        shutil.rmtree(legacy, ignore_errors=True)

    def _resolve_media(self, project: Project) -> None:
        """Follow media through moves of the whole working folder.

        `relPath` (relative to the folder that holds the bundle) wins when it points to an
        existing file; otherwise the stored absolute path is kept. Assets without `relPath`
        (older projects) get one, so the project becomes portable on its next save.
        """
        base = self.path.parent.resolve()
        for asset in project.assets:
            if asset.rel_path:
                candidate = (base / asset.rel_path).resolve()
                if candidate.is_file():
                    asset.path = str(candidate)
                    continue
            if not asset.rel_path and Path(asset.path).is_file():
                # On another Windows drive only the absolute path can work.
                with contextlib.suppress(ValueError):
                    asset.rel_path = Path(os.path.relpath(asset.path, base)).as_posix()

    def save(self, project: Project) -> None:
        """Atomically write ``project.json`` (refused for read-only files)."""
        with self._lock:
            if self.read_only or not can_write(project.dump()):
                raise ReadOnlyProjectError(
                    f"{self.project_file} requires a newer Video-Flow to be written"
                )
            save_atomic(self.project_file, dumps_project(project))
            self._project = project

    @property
    def project(self) -> Project:
        with self._lock:
            if self._project is None:
                return self.load()
            return self._project

    def revision(self) -> int:
        return self.project.revision

    def commit(
        self, base_revision: int, commands: Sequence[Command]
    ) -> tuple[Project, list[Command]]:
        """Apply a client batch with optimistic locking; returns the project and inverses.

        Raises :class:`StaleRevisionError` when ``base_revision`` is not the current one
        and :class:`~videoflow.project.commands.CommandError` when a command is invalid.
        """
        with self._lock:
            current = self.project
            if self.read_only:
                raise ReadOnlyProjectError(f"{self.project_file} is read-only")
            if base_revision != current.revision:
                raise StaleRevisionError(base_revision, current.revision)
            updated, inverses = apply_batch(current, list(commands))
            self.append_history(
                HistoryEntry(
                    revision=updated.revision,
                    base_revision=base_revision,
                    commands=list(commands),
                    inverses=inverses,
                )
            )
            self.save(updated)
            return updated, inverses

    # -- history ---------------------------------------------------------------

    def append_history(self, entry: HistoryEntry) -> None:
        line = json.dumps(entry.dump(), ensure_ascii=False, separators=(",", ":")) + "\n"
        with self._lock, open(self.history_file, "ab") as fh:
            fh.write(line.encode("utf-8"))
            fh.flush()
            os.fsync(fh.fileno())

    def read_history(self) -> list[HistoryEntry]:
        """All complete history lines (a torn last line from a crash is ignored)."""
        if not self.history_file.exists():
            return []
        entries = []
        for raw in self.history_file.read_bytes().splitlines():
            if not raw.strip():
                continue
            try:
                entries.append(HistoryEntry.model_validate(json.loads(raw)))
            except (json.JSONDecodeError, ValidationError):
                continue
        return entries

    def _replay_history(self, project: Project) -> Project:
        """Re-apply batches logged after the last saved revision (crash before save)."""
        if self.read_only:
            return project
        for entry in self.read_history():
            if entry.schema_version != project.schema_version:
                continue
            if entry.base_revision != project.revision:
                continue
            try:
                replayed, _ = apply_batch(project, entry.commands)
            except CommandError:
                break
            project = replayed
        return project

    def _remove_stale_temp_files(self) -> None:
        for tmp in self.path.glob(".*.tmp"):
            with contextlib.suppress(OSError):
                tmp.unlink()


def read_raw(path: Path) -> dict[str, Any]:
    """The raw JSON dict of a ``project.json`` (no migration, no validation)."""
    data = json.loads(Path(path).read_bytes())
    if not isinstance(data, dict):
        raise ProjectStoreError(f"{path} must hold a JSON object")
    return data
