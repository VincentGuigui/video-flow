"""Content-hash stage cache (08 D-7, 04 §1 "Cache key", NFR-04).

Each stage output is a directory ``<root>/<stage>/<key>/`` holding JSON and ``.npy``
files plus a ``_meta.json``. It is built in a hidden temp directory next to it and renamed
into place once complete, so an entry is either fully there or absent: a process killed
mid-stage leaves only a temp directory, which :meth:`StageCache.sweep` removes. Resuming
after a crash is a plain rerun; stages whose key already exists are skipped.

The key is the hash of (inputs, stage name, stage version, params). Inputs are asset
content hashes and/or the keys of upstream stages, so a change upstream invalidates every
dependent stage. Engine and model ids belong in ``params``.
"""

from __future__ import annotations

import contextlib
import hashlib
import inspect
import json
import os
import re
import shutil
import time
import uuid
from collections.abc import Awaitable, Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from fractions import Fraction
from pathlib import Path, PurePath
from typing import Any

import numpy as np
import numpy.typing as npt
from pydantic import BaseModel

META_FILE = "_meta.json"
DATA_FILE = "data.json"
TMP_PREFIX = ".tmp-"
KEY_DIGEST_BYTES = 16
_REPLACE_RETRIES = 5
_STAGE_RE = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,63}$")
_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


# ---------------------------------------------------------------- keys


def _canonical_default(obj: object) -> object:
    if isinstance(obj, BaseModel):
        return obj.model_dump(mode="json", by_alias=True)
    if isinstance(obj, PurePath):
        return obj.as_posix()
    if isinstance(obj, Fraction):
        return f"{obj.numerator}/{obj.denominator}"
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, (set, frozenset)):
        return sorted(obj, key=repr)
    if isinstance(obj, np.generic):
        return obj.item()
    raise TypeError(f"cannot hash parameter of type {type(obj).__name__}")


def canonical_json(obj: object) -> str:
    """Deterministic JSON (sorted keys, no spaces) used for hashing parameters."""
    return json.dumps(
        obj,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=True,
        default=_canonical_default,
    )


def stage_key(
    inputs: str | Sequence[str],
    stage: str,
    version: int | str,
    params: Mapping[str, Any] | None = None,
) -> str:
    """Cache key: hex hash of (inputs, stage, stage version, params).

    ``inputs`` order matters (e.g. a pair of assets is not symmetric unless the caller
    sorts it). Parameter dict order does not.
    """
    _check_stage(stage)
    ins = [inputs] if isinstance(inputs, str) else list(inputs)
    payload = canonical_json(
        {"inputs": ins, "stage": stage, "version": str(version), "params": dict(params or {})}
    )
    return hashlib.blake2b(payload.encode("utf-8"), digest_size=KEY_DIGEST_BYTES).hexdigest()


def _check_stage(stage: str) -> None:
    if not _STAGE_RE.match(stage):
        raise ValueError(f"invalid stage name: {stage!r}")


def _check_name(name: str) -> None:
    if not _NAME_RE.match(name) or name == META_FILE:
        raise ValueError(f"invalid cache file name: {name!r}")


# ---------------------------------------------------------------- file helpers


def _write_file(path: Path, data: bytes) -> None:
    with open(path, "wb") as fh:
        fh.write(data)
        fh.flush()
        os.fsync(fh.fileno())


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


def _rename_dir(src: Path, dst: Path) -> bool:
    """Rename ``src`` to ``dst``; False when ``dst`` already exists (another writer won)."""
    for attempt in range(_REPLACE_RETRIES):
        if dst.exists():
            return False
        try:
            os.rename(src, dst)
            return True
        except FileExistsError:
            return False
        except OSError:
            if dst.exists():
                return False
            # Windows: an antivirus or indexer may briefly hold a file in the new folder.
            if os.name != "nt" or attempt == _REPLACE_RETRIES - 1:
                raise
            time.sleep(0.05 * (attempt + 1))
    return False


def _json_bytes(obj: object) -> bytes:
    if isinstance(obj, BaseModel):
        obj = obj.model_dump(mode="json", by_alias=True)
    return (json.dumps(obj, ensure_ascii=False, indent=1) + "\n").encode("utf-8")


# ---------------------------------------------------------------- entries


@dataclass(frozen=True)
class CacheEntry:
    """A completed (committed) stage output. Read-only."""

    stage: str
    key: str
    path: Path

    def file(self, name: str) -> Path:
        _check_name(name)
        return self.path / name

    @property
    def meta(self) -> dict[str, Any]:
        result: dict[str, Any] = json.loads((self.path / META_FILE).read_text(encoding="utf-8"))
        return result

    def read_json(self, name: str = DATA_FILE) -> Any:
        return json.loads(self.file(name).read_text(encoding="utf-8"))

    def read_npy(self, name: str, *, mmap: bool = False) -> npt.NDArray[Any]:
        arr: npt.NDArray[Any] = np.load(
            self.file(name), allow_pickle=False, mmap_mode="r" if mmap else None
        )
        return arr

    def read_bytes(self, name: str) -> bytes:
        return self.file(name).read_bytes()


class EntryWriter:
    """Collects the files of one stage output in a temp directory until commit."""

    def __init__(self, stage: str, key: str, tmp_dir: Path) -> None:
        self.stage = stage
        self.key = key
        self.dir = tmp_dir
        self.files: list[str] = []

    def path(self, name: str) -> Path:
        """Path for a file written by someone else (e.g. FFmpeg output); registered."""
        _check_name(name)
        if name not in self.files:
            self.files.append(name)
        return self.dir / name

    def write_bytes(self, name: str, data: bytes) -> Path:
        p = self.path(name)
        _write_file(p, data)
        return p

    def write_json(self, obj: object, name: str = DATA_FILE) -> Path:
        return self.write_bytes(name, _json_bytes(obj))

    def write_npy(self, name: str, arr: npt.ArrayLike) -> Path:
        if not name.endswith(".npy"):
            name += ".npy"
        p = self.path(name)
        with open(p, "wb") as fh:
            np.save(fh, np.asarray(arr), allow_pickle=False)
            fh.flush()
            os.fsync(fh.fileno())
        return p


type Producer = Callable[[EntryWriter], None]
type AsyncProducer = Callable[[EntryWriter], Awaitable[None] | None]


class StageCache:
    """Stage outputs keyed by :func:`stage_key`, stored under ``root``.

    For a project bundle the root is ``Bundle.analysis_dir``. Safe across processes: two
    writers of the same key both compute, the first rename wins, the other is discarded.
    """

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)

    def entry_dir(self, stage: str, key: str) -> Path:
        _check_stage(stage)
        if not re.fullmatch(r"[0-9a-f]{8,128}", key):
            raise ValueError(f"invalid cache key: {key!r}")
        return self.root / stage / key

    def get(self, stage: str, key: str) -> CacheEntry | None:
        d = self.entry_dir(stage, key)
        if (d / META_FILE).is_file():
            return CacheEntry(stage, key, d)
        return None

    def contains(self, stage: str, key: str) -> bool:
        return self.get(stage, key) is not None

    @contextlib.contextmanager
    def writer(
        self, stage: str, key: str, meta: Mapping[str, Any] | None = None
    ) -> Iterator[EntryWriter]:
        """Build an entry; it is committed when the block exits normally, else discarded."""
        final = self.entry_dir(stage, key)
        final.parent.mkdir(parents=True, exist_ok=True)
        tmp = final.parent / f"{TMP_PREFIX}{key}-{uuid.uuid4().hex[:12]}"
        tmp.mkdir()
        w = EntryWriter(stage, key, tmp)
        try:
            yield w
            info = {
                "stage": stage,
                "key": key,
                "createdAt": datetime.now(UTC).isoformat(timespec="milliseconds"),
                "files": sorted(w.files),
                **dict(meta or {}),
            }
            _write_file(tmp / META_FILE, _json_bytes(info))
            _fsync_dir(tmp)
            if _rename_dir(tmp, final):
                _fsync_dir(final.parent)
        finally:
            if tmp.exists():
                shutil.rmtree(tmp, ignore_errors=True)

    def ensure(
        self,
        stage: str,
        key: str,
        produce: Producer,
        meta: Mapping[str, Any] | None = None,
    ) -> tuple[CacheEntry, bool]:
        """Return the entry, producing it first if missing. The bool is True if computed."""
        if (hit := self.get(stage, key)) is not None:
            return hit, False
        with self.writer(stage, key, meta) as w:
            produce(w)
        return self._committed(stage, key), True

    async def aensure(
        self,
        stage: str,
        key: str,
        produce: AsyncProducer,
        meta: Mapping[str, Any] | None = None,
    ) -> tuple[CacheEntry, bool]:
        """Async variant of :meth:`ensure`; ``produce`` may be a coroutine function."""
        if (hit := self.get(stage, key)) is not None:
            return hit, False
        with self.writer(stage, key, meta) as w:
            res = produce(w)
            if inspect.isawaitable(res):
                await res
        return self._committed(stage, key), True

    def _committed(self, stage: str, key: str) -> CacheEntry:
        entry = self.get(stage, key)
        if entry is None:  # pragma: no cover - rename succeeded or another writer won
            raise RuntimeError(f"cache entry {stage}/{key} missing after commit")
        return entry

    def invalidate(self, stage: str, key: str) -> bool:
        d = self.entry_dir(stage, key)
        if not d.exists():
            return False
        # Rename first so readers never see a half-deleted entry.
        trash = d.parent / f"{TMP_PREFIX}del-{key}-{uuid.uuid4().hex[:12]}"
        try:
            os.rename(d, trash)
        except OSError:
            trash = d
        shutil.rmtree(trash, ignore_errors=True)
        return True

    def keys(self, stage: str) -> list[str]:
        d = self.root / stage
        if not d.is_dir():
            return []
        return sorted(
            p.name for p in d.iterdir() if not p.name.startswith(".") and (p / META_FILE).is_file()
        )

    def sweep(self, max_age_s: float = 3600.0) -> int:
        """Remove temp directories left by crashed writers; returns how many were removed.

        Only temp directories older than ``max_age_s`` are removed, so a writer still
        running in another process is not disturbed.
        """
        if not self.root.is_dir():
            return 0
        now = time.time()
        removed = 0
        for stage_dir in self.root.iterdir():
            if not stage_dir.is_dir():
                continue
            for p in stage_dir.iterdir():
                if not p.name.startswith(TMP_PREFIX):
                    continue
                try:
                    age = now - p.stat().st_mtime
                except OSError:
                    continue
                if age >= max_age_s:
                    shutil.rmtree(p, ignore_errors=True)
                    removed += 1
        return removed
