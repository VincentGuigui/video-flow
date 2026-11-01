"""Explicit, cancellable model downloads; inference never approves its own download."""

import asyncio
import contextlib
import importlib.util
import json
import shutil
from pathlib import Path
from typing import Any

from videoflow.engines.manifest import load_manifest, models_dir
from videoflow.jobs.workers import EngineSpec, WorkerPool, report_progress
from videoflow.preferences import Preferences, required_models


def model_folder(key: str) -> Path:
    """The Hugging Face cache folder of a model (every revision, blobs and snapshots)."""
    spec = load_manifest().get(key)
    return models_dir() / "hf" / ("models--" + spec.repo.replace("/", "--"))


def stored_files(folder: Path) -> set[Path]:
    """The real files behind a model folder.

    The Hugging Face cache links snapshots to blobs, and blobs may themselves link into a
    shared store (`models/hf/blobs/`); on Windows without symlinks they are plain files.
    """
    files: set[Path] = set()
    if folder.is_dir():
        for item in folder.rglob("*"):
            with contextlib.suppress(OSError):
                real = item.resolve()
                if real.is_file():
                    files.add(real)
    return files


def disk_size(key: str) -> int:
    """Bytes the model occupies, counting each real file once."""
    total = 0
    for real in stored_files(model_folder(key)):
        with contextlib.suppress(OSError):
            total += real.stat().st_size
    return total


SIZES_FILE = "download-sizes.json"
"""Download sizes from the Hub, cached per `repo@revision` in the models folder."""


def _sizes_cache() -> dict[str, int]:
    with contextlib.suppress(OSError, ValueError):
        data = json.loads((models_dir() / SIZES_FILE).read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return {k: int(v) for k, v in data.items()}
    return {}


def _size_key(key: str) -> str:
    spec = load_manifest().get(key)
    return f"{spec.repo}@{spec.revision}"


def download_size(key: str) -> int | None:
    """Bytes of the pinned files, if the Hub was already asked (no network here)."""
    return _sizes_cache().get(_size_key(key))


def fetch_download_sizes(keys: list[str]) -> dict[str, int | None]:
    """Ask the Hub for the sizes of the pinned files of `keys` not cached yet.

    Metadata only (no model file is downloaded). Unreachable Hub: sizes stay unknown.
    """
    from huggingface_hub import HfApi

    cache = _sizes_cache()
    api = HfApi()
    for key in keys:
        name = _size_key(key)
        if name in cache:
            continue
        spec = load_manifest().get(key)
        with contextlib.suppress(Exception):
            infos = api.get_paths_info(spec.repo, spec.files, revision=spec.revision)
            sizes = [getattr(info, "size", None) for info in infos]
            if len(sizes) == len(spec.files) and all(isinstance(s, int) for s in sizes):
                cache[name] = sum(int(s) for s in sizes if s is not None)
    with contextlib.suppress(OSError):
        models_dir().mkdir(parents=True, exist_ok=True)
        (models_dir() / SIZES_FILE).write_text(json.dumps(cache, indent=2), encoding="utf-8")
    return {key: cache.get(_size_key(key)) for key in keys}


def model_state(key: str) -> str:
    spec = load_manifest().get(key)
    snapshots = model_folder(key) / "snapshots"
    current = snapshots / spec.revision
    if all(
        (current / name).is_file() and (current / name).stat().st_size > 0 for name in spec.files
    ):
        return "up-to-date"
    if snapshots.is_dir() and any(
        p.is_dir() and p.name != spec.revision for p in snapshots.iterdir()
    ):
        return "obsolete"
    return "missing"


def missing_models(preferences: Preferences) -> list[str]:
    return [key for key in required_models(preferences) if model_state(key) != "up-to-date"]


class Downloader:
    def download(self, key: str) -> None:
        models_dir()
        from huggingface_hub import hf_hub_download

        spec = load_manifest().get(key)
        count = len(spec.files)
        for index, name in enumerate(spec.files):
            report_progress(index / count, f"{name} · file {index + 1}/{count}")

            hf_hub_download(
                spec.repo,
                name,
                revision=spec.revision,
                cache_dir=models_dir() / "hf",
            )
        if model_state(key) != "up-to-date":
            raise ValueError("Downloaded model is incomplete")


class ModelDownloads:
    def __init__(self) -> None:
        self.workers = WorkerPool(
            {"download": EngineSpec("videoflow.engines.downloads:Downloader")}
        )
        self.jobs: dict[str, dict[str, Any]] = {}
        self.tasks: dict[str, asyncio.Task[None]] = {}

    def status(self, preferences: Preferences) -> dict[str, Any]:
        required = required_models(preferences)
        models = []
        for key, spec in load_manifest().models.items():
            if not spec.in_editor:
                continue
            modules = (
                ("torch", "transformers")
                if spec.purpose == "summary"
                else (("faster_whisper",) if key == "faster-whisper-tiny" else ("onnxruntime",))
            )
            models.append(
                {
                    "id": key,
                    "name": spec.repo,
                    "purpose": spec.purpose,
                    "goal": spec.goal,
                    "state": model_state(key),
                    "size": download_size(key),
                    "disk": disk_size(key),
                    "revision": spec.revision,
                    "required": key in required,
                    "license": spec.license,
                    "runtimeMissing": [m for m in modules if importlib.util.find_spec(m) is None],
                    "download": self.jobs.get(key),
                }
            )
        return {"directory": str(models_dir()), "models": models}

    def submit(self, key: str) -> dict[str, Any]:
        if not load_manifest().get(key).in_editor:
            raise ValueError(f"{key} is not used by the editor")
        if key in self.tasks and not self.tasks[key].done():
            return self.jobs[key]
        job: dict[str, Any] = {"state": "queued", "progress": 0, "phase": "Waiting", "error": None}
        self.jobs[key] = job

        async def run() -> None:
            try:
                job["state"] = "running"

                def progress(value: float, message: str | None) -> None:
                    job.update(progress=value, phase=message or "Downloading")

                await self.workers.call("download", "download", key, on_progress=progress)
                job.update(state="done", progress=1, phase="Ready")
            except asyncio.CancelledError:
                job.update(state="cancelled", phase="Cancelled; download can be resumed")
            except Exception as exc:
                job.update(state="failed", error=str(exc))

        self.tasks[key] = asyncio.create_task(run())
        return job

    async def cancel(self, key: str) -> None:
        task = self.tasks.get(key)
        if task and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            self.jobs[key].update(state="cancelled", phase="Cancelled; download can be resumed")

    def remove(self, key: str) -> None:
        """Delete a model's files (every revision); it can be downloaded again later."""
        load_manifest().get(key)
        if key in self.tasks and not self.tasks[key].done():
            raise ValueError("Cancel the download before removing the model")
        folder = model_folder(key)
        mine = stored_files(folder)
        others = set().union(
            *(
                stored_files(other)
                for other in (models_dir() / "hf").glob("models--*")
                if other != folder
            )
        )
        shutil.rmtree(folder, ignore_errors=True)
        # Shared-store files only this model used (outside its folder) go too.
        for real in mine - others:
            with contextlib.suppress(OSError):
                real.unlink()
        if folder.exists():
            raise ValueError(f"Some files of {key} are in use; close the app and remove again")
        self.jobs.pop(key, None)

    async def close(self) -> None:
        for key in list(self.tasks):
            await self.cancel(key)
        await self.workers.aclose()
