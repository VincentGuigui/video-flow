from __future__ import annotations

import asyncio
import shutil
import time
from pathlib import Path
from typing import Any

import pytest

from videoflow.api.events import parse_event
from videoflow.jobs.registry import (
    InMemoryJobRegistry,
    JobFailedError,
    RunContext,
    ffmpeg_job,
    worker_job,
)
from videoflow.jobs.types import (
    JobContext,
    JobDoneEvent,
    JobEvent,
    JobProgressEvent,
    JobSpec,
    Priority,
)
from videoflow.jobs.workers import EngineSpec, WorkerPool

needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")


@pytest.fixture
async def registry():
    reg = InMemoryJobRegistry(max_concurrent=1)
    try:
        yield reg
    finally:
        await reg.aclose()


def _gate_job(gate: asyncio.Event):
    async def fn(ctx: JobContext) -> dict[str, Any] | None:
        await gate.wait()
        return None

    return fn


async def test_priority_order_and_fifo(registry: InMemoryJobRegistry):
    gate = asyncio.Event()
    order: list[str] = []

    def rec(name: str):
        async def fn(ctx: JobContext) -> dict[str, Any]:
            order.append(name)
            return {"name": name}

        return fn

    blocker = await registry.submit(JobSpec(kind="block"), _gate_job(gate))
    ids = {}
    for name, prio in [
        ("render", Priority.RENDER),
        ("bg", Priority.BACKGROUND),
        ("analyse1", Priority.ANALYSIS),
        ("proxy", Priority.INGEST),
        ("analyse2", Priority.ANALYSIS),
        ("ui", Priority.INTERACTIVE),
    ]:
        ids[name] = (await registry.submit(JobSpec(kind=name, priority=prio), rec(name))).id
    assert registry.get(ids["ui"]).state == "queued"  # type: ignore[union-attr]
    gate.set()
    for job_id in ids.values():
        await registry.wait(job_id, timeout=5)
    assert order == ["ui", "proxy", "analyse1", "analyse2", "render", "bg"]
    assert registry.get(blocker.id).state == "succeeded"  # type: ignore[union-attr]
    assert registry.get(ids["proxy"]).result == {"name": "proxy"}  # type: ignore[union-attr]


async def test_max_concurrent_respected():
    reg = InMemoryJobRegistry(max_concurrent=2)
    running = 0
    peak = 0

    async def fn(ctx: JobContext) -> None:
        nonlocal running, peak
        running += 1
        peak = max(peak, running)
        await asyncio.sleep(0.02)
        running -= 1

    jobs = [await reg.submit(JobSpec(kind="x"), fn) for _ in range(6)]
    for j in jobs:
        await reg.wait(j.id, timeout=5)
    assert peak == 2
    await reg.aclose()


async def test_events_progress_throttled_and_done():
    sink: list[JobEvent] = []
    reg = InMemoryJobRegistry(on_event=sink.append)
    stream = reg.subscribe()

    async def fn(ctx: JobContext) -> dict[str, Any]:
        for i in range(1, 1001):
            ctx.report(i / 1000)  # 1000 reports in a tight loop
        return {"ok": True}

    job = await reg.submit(JobSpec(kind="proxy", project_id="prj_1", asset_id="ast_1"), fn)
    got: list[JobEvent] = []
    async for ev in stream:
        got.append(ev)
        if isinstance(ev, JobDoneEvent):
            break
    await stream.aclose()  # type: ignore[attr-defined]
    assert got == sink
    progress = [e for e in got if isinstance(e, JobProgressEvent)]
    assert progress[0].progress == 0.0 and progress[0].state == "running"
    assert progress[-1].progress == 1.0
    assert 3 <= len(progress) <= 110  # throttled to >= 1 % steps
    done = got[-1]
    assert isinstance(done, JobDoneEvent)
    assert done.state == "succeeded" and done.result == {"ok": True}
    assert done.job_id == job.id and done.asset_id == "ast_1"
    # the events are members of the API event union
    for ev in got:
        assert parse_event(ev.dump()) == ev
    final = reg.get(job.id)
    assert final is not None and final.progress == 1.0 and final.ended_at
    await reg.aclose()


async def test_failure_is_recorded(registry: InMemoryJobRegistry):
    async def fn(ctx: JobContext) -> None:
        raise JobFailedError("nope")

    job = await registry.submit(JobSpec(kind="x"), fn)
    final = await registry.wait(job.id, timeout=5)
    assert final.state == "failed" and final.error == "nope"


async def test_cancel_queued_and_running(registry: InMemoryJobRegistry):
    gate = asyncio.Event()
    running = await registry.submit(JobSpec(kind="block"), _gate_job(gate))
    queued = await registry.submit(JobSpec(kind="later"), _gate_job(gate))
    await asyncio.sleep(0)
    assert await registry.cancel(queued.id)
    assert registry.get(queued.id).state == "cancelled"  # type: ignore[union-attr]
    assert await registry.cancel(running.id)
    final = await registry.wait(running.id, timeout=1)
    assert final.state == "cancelled"
    assert not await registry.cancel(running.id)
    assert not await registry.cancel("job_missing")


async def test_cooperative_cancel_flag(registry: InMemoryJobRegistry):
    seen: list[bool] = []

    async def fn(ctx: JobContext) -> None:
        while True:
            seen.append(ctx.cancelled)
            try:
                await asyncio.sleep(0.01)
            except asyncio.CancelledError:
                seen.append(ctx.cancelled)
                ctx.raise_if_cancelled()

    job = await registry.submit(JobSpec(kind="x"), fn)
    await asyncio.sleep(0.05)
    await registry.cancel(job.id)
    assert (await registry.wait(job.id, timeout=1)).state == "cancelled"
    assert seen[-1] is True


async def test_list_and_prune():
    reg = InMemoryJobRegistry(keep_finished=2)

    async def fn(ctx: JobContext) -> None:
        return None

    jobs = [
        await reg.submit(JobSpec(kind="x", project_id="a" if i % 2 else "b"), fn) for i in range(5)
    ]
    for j in jobs:
        await reg.wait(j.id, timeout=5)
    assert [j.id for j in reg.list()] == [j.id for j in jobs]
    assert len(reg.list("a")) == 2
    assert reg.prune() == 3
    assert [j.id for j in reg.list()] == [j.id for j in jobs[-2:]]
    await reg.aclose()


@needs_ffmpeg
async def test_ffmpeg_job_progress(registry: InMemoryJobRegistry, tmp_path: Path):
    out = tmp_path / "o.mp4"
    args = ["-f", "lavfi", "-i", "testsrc2=s=160x90:r=25:d=1", "-c:v", "libx264",
            "-preset", "ultrafast", "-y", str(out)]  # fmt: skip
    events = registry.subscribe()
    job = await registry.submit(JobSpec(kind="proxy"), ffmpeg_job(args, duration_us=1_000_000))
    final = await registry.wait(job.id, timeout=30)
    assert final.state == "succeeded" and out.exists()
    got = []
    while True:
        ev = await asyncio.wait_for(anext(events), 1)
        got.append(ev)
        if isinstance(ev, JobDoneEvent):
            break
    assert any(isinstance(e, JobProgressEvent) and e.progress == 1.0 for e in got)


@needs_ffmpeg
async def test_ffmpeg_job_failure(registry: InMemoryJobRegistry, tmp_path: Path):
    job = await registry.submit(
        JobSpec(kind="proxy"), ffmpeg_job(["-i", str(tmp_path / "missing.mp4"), "-f", "null", "-"])
    )
    final = await registry.wait(job.id, timeout=30)
    assert final.state == "failed" and "missing.mp4" in (final.error or "")


@needs_ffmpeg
async def test_cancel_ffmpeg_job_within_one_second(registry: InMemoryJobRegistry):
    started = asyncio.Event()

    async def fn(ctx: JobContext) -> None:
        assert isinstance(ctx, RunContext)
        started.set()
        await ctx.run_ffmpeg(
            ["-re", "-f", "lavfi", "-i", "testsrc2=s=160x90:r=25", "-f", "null", "-"],
            duration_us=600_000_000,
        )

    job = await registry.submit(JobSpec(kind="render", priority=Priority.RENDER), fn)
    await asyncio.wait_for(started.wait(), 5)
    await asyncio.sleep(0.8)  # let ffmpeg get going
    t0 = time.monotonic()
    await registry.cancel(job.id)
    final = await registry.wait(job.id, timeout=2)
    assert time.monotonic() - t0 <= 1.0
    assert final.state == "cancelled"


async def test_cancel_worker_job_within_one_second_and_respawn(registry: InMemoryJobRegistry):
    pool = WorkerPool({"sleepy": EngineSpec("tests.jobs.fake_engines:SleepyEngine")})
    try:
        pid = await pool.call("sleepy", "pid")
        job = await registry.submit(
            JobSpec(kind="analyse"), worker_job(pool, "sleepy", "sleep", 30.0, steps=300)
        )
        for _ in range(100):  # wait for the first progress report from the worker
            await asyncio.sleep(0.02)
            j = registry.get(job.id)
            if j is not None and j.progress > 0:
                break
        t0 = time.monotonic()
        await registry.cancel(job.id)
        final = await registry.wait(job.id, timeout=2)
        assert time.monotonic() - t0 <= 1.0
        assert final.state == "cancelled"
        assert pool.worker("sleepy").restarts == 1
        assert await pool.call("sleepy", "pid") != pid
        ok = await registry.submit(JobSpec(kind="analyse"), worker_job(pool, "sleepy", "echo", 5))
        assert (await registry.wait(ok.id, timeout=30)).result == {"value": 5}
    finally:
        await pool.aclose()
