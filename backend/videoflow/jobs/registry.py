"""In-memory asyncio job registry with priorities (08 D-7).

There is no persistent job table: after a crash the client resubmits and the stage cache
skips completed work. Jobs wait in a priority queue (lower :class:`Priority` first, FIFO
within a priority) and at most ``max_concurrent`` run at once. Each job is an asyncio
task; cancelling it sets ``JobContext.cancel_event`` and cancels the task, which stops
FFmpeg (``media.ffmpeg.run``) or kills and respawns the ML worker (``jobs.workers``).

Events are the ``job.progress`` / ``job.done`` members of the ``api.events`` union. They
go to every :meth:`InMemoryJobRegistry.subscribe` stream and to the optional ``on_event``
sink (the API event bus). Progress events are throttled.
"""

from __future__ import annotations

import asyncio
import contextlib
import heapq
import itertools
import time
from collections.abc import AsyncIterator, Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from videoflow.core import ids
from videoflow.jobs.types import (
    Job,
    JobContext,
    JobDoneEvent,
    JobEvent,
    JobFn,
    JobProgressEvent,
    JobSpec,
)
from videoflow.jobs.workers import ProgressFn, WorkerPool
from videoflow.media import ffmpeg

PROGRESS_MIN_STEP = 0.01
PROGRESS_MIN_INTERVAL_S = 0.25
SUBSCRIBER_QUEUE_SIZE = 1000
DEFAULT_MAX_CONCURRENT = 2

type EventSink = Callable[[JobEvent], None]


class JobFailedError(RuntimeError):
    """Raised inside a job function to fail it with a clean message."""


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


class RunContext:
    """The :class:`JobContext` handed to a running job function.

    Beyond the protocol it exposes ``cancel_event`` and FFmpeg / worker helpers that
    forward progress and cancellation.
    """

    def __init__(self, registry: InMemoryJobRegistry, job_id: str) -> None:
        self.job_id = job_id
        self.cancel_event = asyncio.Event()
        self._registry = registry
        self._last_progress = -1.0
        self._last_emit = 0.0

    def report(self, progress: float, message: str | None = None) -> None:
        progress = min(max(float(progress), 0.0), 1.0)
        now = time.monotonic()
        emit = (
            progress >= 1.0
            or progress - self._last_progress >= PROGRESS_MIN_STEP
            or now - self._last_emit >= PROGRESS_MIN_INTERVAL_S
        ) and progress != self._last_progress
        self._registry._set_progress(self.job_id, progress, message, emit=emit)
        if emit:
            self._last_progress = progress
            self._last_emit = now

    @property
    def cancelled(self) -> bool:
        return self.cancel_event.is_set()

    def raise_if_cancelled(self) -> None:
        if self.cancel_event.is_set():
            raise asyncio.CancelledError()

    async def run_ffmpeg(
        self,
        args: list[str],
        *,
        duration_us: int | None = None,
        progress_span: tuple[float, float] = (0.0, 1.0),
        ffmpeg_path: Path | str | None = None,
    ) -> ffmpeg.Result:
        """Run FFmpeg with progress mapped into ``progress_span``; raises on failure."""
        lo, hi = progress_span

        def on_progress(p: ffmpeg.Progress) -> None:
            if p.fraction is not None:
                self.report(lo + (hi - lo) * p.fraction)

        res = await ffmpeg.run(
            args,
            on_progress=on_progress,
            cancel=self.cancel_event,
            duration_us=duration_us,
            ffmpeg=ffmpeg_path,
        )
        if res.cancelled:
            raise asyncio.CancelledError()
        if not res.ok:
            tail = res.stderr_tail.strip().splitlines()[-5:]
            raise JobFailedError(f"ffmpeg exited with {res.returncode}: " + " | ".join(tail))
        return res

    async def call_worker(
        self,
        pool: WorkerPool,
        engine: str,
        method: str,
        *args: Any,
        progress_span: tuple[float, float] = (0.0, 1.0),
        **kwargs: Any,
    ) -> Any:
        """Call an engine method in its worker, forwarding progress into ``progress_span``."""
        lo, hi = progress_span

        def on_progress(p: float, msg: str | None) -> None:
            self.report(lo + (hi - lo) * p, msg)

        progress: ProgressFn = on_progress
        return await pool.call(engine, method, *args, on_progress=progress, **kwargs)


@dataclass
class _Entry:
    job: Job
    fn: JobFn
    seq: int
    ctx: RunContext | None = None
    task: asyncio.Task[None] | None = None
    done: asyncio.Event = field(default_factory=asyncio.Event)


class InMemoryJobRegistry:
    """Implements :class:`videoflow.jobs.types.JobRegistry`.

    Use from one asyncio loop (``SelectorEventLoop`` or Windows ``ProactorEventLoop``).
    Finished jobs are kept for listing until :meth:`prune` (the newest ``keep_finished``).
    """

    def __init__(
        self,
        max_concurrent: int = DEFAULT_MAX_CONCURRENT,
        *,
        on_event: EventSink | None = None,
        keep_finished: int = 500,
    ) -> None:
        if max_concurrent < 1:
            raise ValueError("max_concurrent must be >= 1")
        self.max_concurrent = max_concurrent
        self.keep_finished = keep_finished
        self._on_event = on_event
        self._entries: dict[str, _Entry] = {}
        self._queue: list[tuple[int, int, str]] = []
        self._running: set[str] = set()
        self._seq = itertools.count()
        self._subscribers: set[asyncio.Queue[JobEvent]] = set()
        self._closed = False

    # ------------------------------------------------------------ public API

    async def submit(self, spec: JobSpec, fn: JobFn) -> Job:
        if self._closed:
            raise RuntimeError("job registry is closed")
        job = Job(
            id=ids.new_id(ids.JOB),
            kind=spec.kind,
            project_id=spec.project_id,
            asset_id=spec.asset_id,
            stage=spec.stage,
            priority=int(spec.priority),
            params_hash=spec.params_hash,
        )
        entry = _Entry(job=job, fn=fn, seq=next(self._seq))
        self._entries[job.id] = entry
        heapq.heappush(self._queue, (job.priority, entry.seq, job.id))
        self._dispatch()
        return job.model_copy()

    async def cancel(self, job_id: str) -> bool:
        """Cancel a queued or running job; False if unknown or already finished."""
        entry = self._entries.get(job_id)
        if entry is None or entry.job.done:
            return False
        if entry.task is None:  # still queued
            self._finish(entry, "cancelled")
            return True
        if entry.ctx is not None:
            entry.ctx.cancel_event.set()
        entry.task.cancel()
        return True

    def get(self, job_id: str) -> Job | None:
        entry = self._entries.get(job_id)
        return entry.job.model_copy() if entry else None

    def list(self, project_id: str | None = None) -> list[Job]:
        return [
            e.job.model_copy()
            for e in sorted(self._entries.values(), key=lambda e: e.seq)
            if project_id is None or e.job.project_id == project_id
        ]

    async def wait(self, job_id: str, timeout: float | None = None) -> Job:  # noqa: ASYNC109
        """Wait until the job reaches a terminal state and return its final record."""
        entry = self._entries[job_id]
        await asyncio.wait_for(entry.done.wait(), timeout)
        return entry.job.model_copy()

    def subscribe(self) -> AsyncIterator[JobEvent]:
        """Job events from the moment of this call. A slow consumer loses its oldest events.

        Close the iterator (``aclose()`` or leaving ``async for``) to unsubscribe.
        """
        q: asyncio.Queue[JobEvent] = asyncio.Queue(maxsize=SUBSCRIBER_QUEUE_SIZE)
        self._subscribers.add(q)
        return self._stream(q)

    async def _stream(self, q: asyncio.Queue[JobEvent]) -> AsyncIterator[JobEvent]:
        try:
            while True:
                yield await q.get()
        finally:
            self._subscribers.discard(q)

    def prune(self) -> int:
        """Drop the oldest finished jobs beyond ``keep_finished``; returns how many."""
        finished = sorted((e for e in self._entries.values() if e.job.done), key=lambda e: e.seq)
        drop = finished[: max(len(finished) - self.keep_finished, 0)]
        for e in drop:
            del self._entries[e.job.id]
        return len(drop)

    async def aclose(self, timeout: float = 5.0) -> None:  # noqa: ASYNC109
        """Cancel every queued and running job and wait for them to stop."""
        self._closed = True
        for job_id in [e.job.id for e in self._entries.values() if not e.job.done]:
            await self.cancel(job_id)
        tasks = [e.task for e in self._entries.values() if e.task is not None and not e.task.done()]
        if tasks:
            await asyncio.wait(tasks, timeout=timeout)

    # ------------------------------------------------------------ internals

    def _dispatch(self) -> None:
        while self._queue and len(self._running) < self.max_concurrent:
            _, _, job_id = heapq.heappop(self._queue)
            entry = self._entries.get(job_id)
            if entry is None or entry.job.state != "queued":
                continue  # cancelled while queued, or pruned
            self._start(entry)

    def _start(self, entry: _Entry) -> None:
        job = entry.job
        job.state = "running"
        job.started_at = _now()
        entry.ctx = RunContext(self, job.id)
        self._running.add(job.id)
        self._emit(
            JobProgressEvent(
                job_id=job.id,
                kind=job.kind,
                project_id=job.project_id,
                asset_id=job.asset_id,
                stage=job.stage,
                state="running",
                progress=0.0,
            )
        )
        entry.task = asyncio.create_task(self._run(entry), name=f"job-{job.id}")

    async def _run(self, entry: _Entry) -> None:
        assert entry.ctx is not None
        ctx: JobContext = entry.ctx
        try:
            result = await entry.fn(ctx)
        except asyncio.CancelledError:
            self._finish(entry, "cancelled")
        except Exception as exc:  # noqa: BLE001 - reported on the job
            self._finish(entry, "failed", error=str(exc) or type(exc).__name__)
        else:
            if entry.ctx.cancelled:
                self._finish(entry, "cancelled")
            else:
                self._finish(entry, "succeeded", result=result)
        finally:
            self._running.discard(entry.job.id)
            if not self._closed:
                self._dispatch()

    def _finish(
        self,
        entry: _Entry,
        state: Literal["succeeded", "failed", "cancelled"],
        *,
        error: str | None = None,
        result: dict[str, Any] | None = None,
    ) -> None:
        job = entry.job
        if job.done:
            return
        job.state = state
        job.ended_at = _now()
        job.error = error
        job.result = result
        if state == "succeeded":
            job.progress = 1.0
        entry.done.set()
        self._emit(
            JobDoneEvent(
                job_id=job.id,
                kind=job.kind,
                project_id=job.project_id,
                asset_id=job.asset_id,
                state=state,
                error=error,
                result=result,
            )
        )

    def _set_progress(
        self, job_id: str, progress: float, message: str | None, *, emit: bool
    ) -> None:
        entry = self._entries.get(job_id)
        if entry is None or entry.job.done:
            return
        job = entry.job
        job.progress = progress
        if message is not None:
            job.message = message
        if emit:
            self._emit(
                JobProgressEvent(
                    job_id=job.id,
                    kind=job.kind,
                    project_id=job.project_id,
                    asset_id=job.asset_id,
                    stage=job.stage,
                    state="running",
                    progress=progress,
                    message=job.message,
                )
            )

    def _emit(self, event: JobEvent) -> None:
        for q in self._subscribers:
            if q.full():
                with contextlib.suppress(asyncio.QueueEmpty):
                    q.get_nowait()
            q.put_nowait(event)
        if self._on_event is not None:
            self._on_event(event)


# ---------------------------------------------------------------- job function helpers


def ffmpeg_job(
    args: Sequence[str],
    *,
    duration_us: int | None = None,
    ffmpeg_path: Path | str | None = None,
) -> JobFn:
    """A job that runs one FFmpeg command with progress and cancellation."""

    async def fn(ctx: JobContext) -> dict[str, Any] | None:
        if not isinstance(ctx, RunContext):
            raise TypeError("ffmpeg_job needs the registry's RunContext")
        res = await ctx.run_ffmpeg(list(args), duration_us=duration_us, ffmpeg_path=ffmpeg_path)
        return {"returncode": res.returncode}

    return fn


def worker_job(pool: WorkerPool, engine: str, method: str, *args: Any, **kwargs: Any) -> JobFn:
    """A job that runs one engine call in its worker; the result must be a dict or None."""

    async def fn(ctx: JobContext) -> dict[str, Any] | None:
        if not isinstance(ctx, RunContext):
            raise TypeError("worker_job needs the registry's RunContext")
        res = await ctx.call_worker(pool, engine, method, *args, **kwargs)
        if res is None or isinstance(res, dict):
            return res
        return {"value": res}

    return fn
