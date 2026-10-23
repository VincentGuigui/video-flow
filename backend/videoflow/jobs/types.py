"""Job contracts: an in-memory asyncio registry (08 D-7), no persistent job table.

Resuming after a crash means resubmitting: completed stages are skipped by the
content-hash stage cache. Events are pushed to subscribers (the SSE stream).
"""

from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import UTC, datetime
from enum import IntEnum
from typing import Any, Literal, Protocol

from pydantic import Field

from videoflow.core.base import CamelModel

type JobState = Literal["queued", "running", "succeeded", "failed", "cancelled"]
TERMINAL_STATES: frozenset[str] = frozenset({"succeeded", "failed", "cancelled"})


class Priority(IntEnum):
    """Lower runs first: probe/proxies make the bin usable before heavy analysis."""

    INTERACTIVE = 0
    INGEST = 10
    ANALYSIS = 20
    RENDER = 30
    BACKGROUND = 40


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


class JobSpec(CamelModel):
    kind: str
    """e.g. ``ingest``, ``proxy``, ``analyse``, ``render``, ``export``."""
    project_id: str | None = None
    asset_id: str | None = None
    stage: str | None = None
    priority: int = Priority.ANALYSIS
    params: dict[str, Any] = Field(default_factory=dict)
    params_hash: str | None = None


class Job(CamelModel):
    id: str
    kind: str
    project_id: str | None = None
    asset_id: str | None = None
    stage: str | None = None
    priority: int = Priority.ANALYSIS
    state: JobState = "queued"
    progress: float = Field(default=0.0, ge=0.0, le=1.0)
    message: str | None = None
    params_hash: str | None = None
    error: str | None = None
    result: dict[str, Any] | None = None
    created_at: str = Field(default_factory=_now)
    started_at: str | None = None
    ended_at: str | None = None

    @property
    def done(self) -> bool:
        return self.state in TERMINAL_STATES


class JobProgressEvent(CamelModel):
    type: Literal["job.progress"] = "job.progress"
    job_id: str
    kind: str
    project_id: str | None = None
    asset_id: str | None = None
    stage: str | None = None
    state: JobState = "running"
    progress: float = Field(ge=0.0, le=1.0)
    message: str | None = None


class JobDoneEvent(CamelModel):
    type: Literal["job.done"] = "job.done"
    job_id: str
    kind: str
    project_id: str | None = None
    asset_id: str | None = None
    state: Literal["succeeded", "failed", "cancelled"]
    error: str | None = None
    result: dict[str, Any] | None = None


type JobEvent = JobProgressEvent | JobDoneEvent


class JobContext(Protocol):
    """Handed to a running job function."""

    job_id: str

    def report(self, progress: float, message: str | None = None) -> None:
        """Progress in [0, 1]; throttled by the registry before it reaches subscribers."""
        ...

    @property
    def cancelled(self) -> bool: ...

    def raise_if_cancelled(self) -> None:
        """Raise ``asyncio.CancelledError`` when cancellation was requested."""
        ...


type JobFn = Callable[[JobContext], Awaitable[dict[str, Any] | None]]


class JobRegistry(Protocol):
    async def submit(self, spec: JobSpec, fn: JobFn) -> Job:
        """Queue a job; returns immediately with its ``queued`` record."""
        ...

    async def cancel(self, job_id: str) -> bool:
        """Request cancellation; FFmpeg is terminated, ML workers are killed and respawned."""
        ...

    def get(self, job_id: str) -> Job | None: ...

    def list(self, project_id: str | None = None) -> list[Job]: ...

    def subscribe(self) -> AsyncIterator[JobEvent]:
        """Stream of job events from now on."""
        ...
