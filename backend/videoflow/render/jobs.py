"""Owned background renders with immutable project snapshots and cancellation."""

import asyncio
import uuid
from typing import Literal

from videoflow.core.base import CamelModel
from videoflow.project.store import Bundle
from videoflow.render.graph import Preset
from videoflow.render.runner import render_project


class RenderJob(CamelModel):
    id: str
    revision: int
    state: Literal["queued", "running", "done", "failed", "cancelled"] = "queued"
    phase: str = "Waiting"
    progress: float = 0
    path: str | None = None
    error: str | None = None


class Renders:
    def __init__(self, bundle: Bundle) -> None:
        self.bundle = bundle
        self.jobs: dict[str, RenderJob] = {}
        self.tasks: dict[str, asyncio.Task[None]] = {}
        self.lock = asyncio.Lock()

    @property
    def active(self) -> bool:
        return any(j.state in ("queued", "running") for j in self.jobs.values())

    def submit(self, preset: Preset, normalize: bool) -> RenderJob:
        snapshot = self.bundle.project.model_copy(deep=True)
        job = RenderJob(id=uuid.uuid4().hex, revision=snapshot.revision)
        self.jobs[job.id] = job

        async def run() -> None:
            try:
                async with self.lock:
                    job.state = "running"

                    def progress(value: float, phase: str) -> None:
                        job.progress, job.phase = min(1, max(0, value)), phase

                    result = await render_project(
                        snapshot,
                        self.bundle,
                        preset=preset,
                        normalize=normalize,
                        render_id=job.id,
                        on_progress=progress,
                    )
                    job.path = str(result.path.resolve())
                    job.state, job.phase, job.progress = "done", "Video ready", 1
            except asyncio.CancelledError:
                job.state, job.phase = "cancelled", "Cancelled"
            except Exception as exc:
                job.state, job.error = "failed", str(exc)

        self.tasks[job.id] = asyncio.create_task(run())
        return job

    async def cancel(self, identifier: str) -> None:
        task = self.tasks[identifier]
        if not task.done():
            task.cancel()
            self.jobs[identifier].state = "cancelled"
        await asyncio.gather(task, return_exceptions=True)

    async def close(self) -> None:
        for identifier in list(self.tasks):
            await self.cancel(identifier)
