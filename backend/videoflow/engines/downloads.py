"""Explicit, cancellable model downloads; inference never approves its own download."""

import asyncio
import importlib.util
from typing import Any

from videoflow.engines.manifest import load_manifest, models_dir
from videoflow.jobs.workers import EngineSpec, WorkerPool, report_progress
from videoflow.preferences import Preferences, required_models


def model_state(key: str) -> str:
    spec = load_manifest().get(key)
    snapshots = models_dir() / "hf" / ("models--" + spec.repo.replace("/", "--")) / "snapshots"
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
                    "state": model_state(key),
                    "revision": spec.revision,
                    "required": key in required,
                    "license": spec.license,
                    "runtimeMissing": [m for m in modules if importlib.util.find_spec(m) is None],
                    "download": self.jobs.get(key),
                }
            )
        return {"directory": str(models_dir()), "models": models}

    def submit(self, key: str) -> dict[str, Any]:
        load_manifest().get(key)
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

    async def close(self) -> None:
        for key in list(self.tasks):
            await self.cancel(key)
        await self.workers.aclose()
