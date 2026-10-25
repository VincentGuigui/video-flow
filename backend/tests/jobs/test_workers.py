from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import numpy as np
import pytest

from videoflow.jobs.workers import (
    EngineSpec,
    EngineWorker,
    WorkerCrashedError,
    WorkerPool,
    WorkerStartError,
    WorkerTaskError,
    resolve_factory,
)

SLEEPY = EngineSpec("tests.jobs.fake_engines:SleepyEngine")
BACKEND = Path(__file__).resolve().parents[2]


@pytest.fixture
async def worker():
    w = EngineWorker("sleepy", SLEEPY)
    try:
        yield w
    finally:
        await w.aclose()


def test_resolve_factory():
    assert resolve_factory("os.path:join") is os.path.join
    with pytest.raises(ValueError):
        resolve_factory("os.path.join")


async def test_call_returns_results(worker: EngineWorker):
    pid = await worker.call("pid")
    assert pid == worker.pid and pid != os.getpid()
    assert await worker.call("echo", "a", suffix="b") == "ab"
    arr = np.arange(12, dtype=np.float32).reshape(3, 4)
    out = await worker.call("echo", arr)
    assert np.array_equal(out, arr)
    # same long-lived process
    assert await worker.call("pid") == pid


async def test_progress_is_forwarded(worker: EngineWorker):
    seen: list[tuple[float, str | None]] = []
    res = await worker.call("sleep", 0.05, steps=5, on_progress=lambda p, m: seen.append((p, m)))
    await asyncio.sleep(0.05)  # progress callbacks are scheduled on the loop
    assert res == "slept"
    assert [p for p, _ in seen] == [0.2, 0.4, 0.6, 0.8, 1.0]
    assert seen[-1][1] == "step 5"


async def test_engine_error_keeps_worker(worker: EngineWorker):
    pid = await worker.call("pid")
    with pytest.raises(WorkerTaskError) as ei:
        await worker.call("fail")
    assert ei.value.exc_type == "ValueError" and "bad input" in str(ei.value)
    assert "Traceback" in ei.value.remote_traceback
    with pytest.raises(WorkerTaskError):
        await worker.call("unpicklable")
    assert await worker.call("pid") == pid


async def test_cancel_kills_within_one_second_and_respawns(worker: EngineWorker):
    pid = await worker.call("pid")
    task = asyncio.create_task(worker.call("sleep", 30.0, steps=300))
    await asyncio.sleep(0.3)
    t0 = time.monotonic()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert time.monotonic() - t0 <= 1.0
    assert worker.restarts == 1
    new_pid = await worker.call("pid")
    assert new_pid != pid
    assert await worker.call("echo", 7) == 7


async def test_crash_is_reported_then_respawned(worker: EngineWorker):
    pid = await worker.call("pid")
    with pytest.raises(WorkerCrashedError):
        await worker.call("crash")
    assert await worker.call("pid") != pid


async def test_factory_failure():
    w = EngineWorker("bad", EngineSpec(SLEEPY.factory, {"fail": True}))
    try:
        with pytest.raises(WorkerStartError, match="engine init failed"):
            await w.start()
        assert w.pid is None
    finally:
        await w.aclose()


async def test_cancel_during_model_startup_kills_worker_without_restarting():
    worker = EngineWorker("initializing", EngineSpec("tests.jobs.fake_engines:SlowInitEngine"))
    task = asyncio.create_task(worker.call("echo", "unused"))
    try:
        deadline = time.monotonic() + 5
        while not worker.alive and time.monotonic() < deadline:  # noqa: ASYNC110 — observe spawned PID
            await asyncio.sleep(0.01)
        assert worker.alive
        await asyncio.sleep(0.1)
        started = time.monotonic()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert time.monotonic() - started < 1
        assert not worker.alive and worker.restarts == 0
        worker.spec = SLEEPY
        assert await worker.call("echo", "ready") == "ready"
    finally:
        task.cancel()
        await worker.aclose()


async def test_pool_routes_by_engine_name():
    pool = WorkerPool({"a": SLEEPY, "b": EngineSpec(SLEEPY.factory, {"tag": "b"})})
    try:
        pa, pb = await asyncio.gather(pool.call("a", "pid"), pool.call("b", "pid"))
        assert pa != pb
        assert await pool.call("a", "pid") == pa
        with pytest.raises(KeyError):
            pool.worker("missing")
    finally:
        await pool.aclose()


def test_spawn_with_main_guard(tmp_path: Path):
    """A script that starts a worker behind the ``__main__`` guard works under spawn."""
    script = tmp_path / "start_worker.py"
    script.write_text(
        textwrap.dedent(
            """
            import asyncio
            import os

            from videoflow.jobs.workers import EngineSpec, EngineWorker

            STARTS = []
            STARTS.append(os.getpid())  # runs again in the child, harmless


            async def main():
                w = EngineWorker("sleepy", EngineSpec("tests.jobs.fake_engines:SleepyEngine"))
                try:
                    child = await w.call("pid")
                    print("OK", child != os.getpid())
                finally:
                    await w.aclose()


            if __name__ == "__main__":
                asyncio.run(main())
            """
        ),
        encoding="utf-8",
    )
    env = {**os.environ, "PYTHONPATH": os.pathsep.join([str(BACKEND), str(tmp_path)])}
    out = subprocess.run(
        [sys.executable, str(script)], capture_output=True, text=True, timeout=60, env=env
    )
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == "OK True"
