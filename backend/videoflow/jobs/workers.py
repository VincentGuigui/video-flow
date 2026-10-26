"""Long-lived ML worker processes, one per engine class (08 D-7).

Each :class:`EngineWorker` owns one ``multiprocessing`` process started with the *spawn*
method (the only one on Windows, and safe with threads on Linux). The process builds its
engine once from a ``"module:callable"`` factory and then serves method calls over a pipe,
one at a time. Cancelling a call kills the process (a running ONNX/CTranslate2 call cannot
be interrupted cooperatively) and a fresh one is spawned in the background.

Spawn re-imports the parent's ``__main__`` module in the child, so any script that starts
workers must guard its entry point with ``if __name__ == "__main__":``; a frozen Windows
build must also call ``multiprocessing.freeze_support()`` there. The factory and every
argument and result must be picklable.

Engine code running in a worker can report progress with :func:`report_progress`.
"""

from __future__ import annotations

import asyncio
import contextlib
import importlib
import itertools
import multiprocessing
import os
import signal
import sys
import threading
import traceback
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

if sys.platform == "win32":
    from multiprocessing.connection import PipeConnection as Connection
else:
    from multiprocessing.connection import Connection

DEFAULT_START_TIMEOUT_S = 120.0
STOP_GRACE_S = 2.0
KILL_JOIN_S = 2.0

ProgressFn = Callable[[float, str | None], Awaitable[None] | None]


class WorkerError(RuntimeError):
    """Base class for worker failures."""


class WorkerStartError(WorkerError):
    """The worker process could not build its engine or did not become ready in time."""


class WorkerCrashedError(WorkerError):
    """The worker process died while serving a call (crash, OOM kill, ...)."""


class WorkerTaskError(WorkerError):
    """The engine method raised inside the worker."""

    def __init__(self, exc_type: str, message: str, tb: str) -> None:
        super().__init__(f"{exc_type}: {message}")
        self.exc_type = exc_type
        self.remote_traceback = tb


# ---------------------------------------------------------------- child side

_child_conn: Connection | None = None
_child_task: int | None = None


def report_progress(progress: float, message: str | None = None) -> None:
    """Report progress of the current call from inside a worker process (no-op elsewhere)."""
    if _child_conn is None or _child_task is None:
        return
    with contextlib.suppress(OSError, ValueError):
        _child_conn.send(("progress", _child_task, float(progress), message))


def resolve_factory(path: str) -> Callable[..., Any]:
    """Import ``"package.module:attr.sub"`` and return the callable."""
    module_name, sep, attr = path.partition(":")
    if not sep or not module_name or not attr:
        raise ValueError(f"factory must be 'module:callable', got {path!r}")
    obj: Any = importlib.import_module(module_name)
    for part in attr.split("."):
        obj = getattr(obj, part)
    if not callable(obj):
        raise TypeError(f"{path} is not callable")
    return obj  # type: ignore[no-any-return]


def _error_payload(exc: BaseException) -> tuple[str, str, str]:
    return (type(exc).__name__, str(exc), "".join(traceback.format_exception(exc)))


def _worker_main(conn: Connection, factory: str, kwargs: dict[str, Any]) -> None:
    """Entry point of the worker process."""
    global _child_conn, _child_task
    # Ctrl+C in a console reaches the whole process group; the parent decides shutdown.
    with contextlib.suppress(ValueError, OSError):
        signal.signal(signal.SIGINT, signal.SIG_IGN)
    _child_conn = conn
    try:
        engine = resolve_factory(factory)(**kwargs)
    except BaseException as exc:  # noqa: BLE001 - reported to the parent
        with contextlib.suppress(OSError):
            conn.send(("failed", None, _error_payload(exc)))
        return
    conn.send(("ready", os.getpid(), None))
    while True:
        try:
            msg = conn.recv()
        except (EOFError, OSError):  # parent gone
            return
        if msg[0] == "stop":
            return
        _, task_id, method, args, kw = msg
        _child_task = task_id
        try:
            result = getattr(engine, method)(*args, **kw)
            reply: tuple[Any, ...] = ("result", task_id, result)
        except Exception as exc:
            reply = ("error", task_id, _error_payload(exc))
        finally:
            _child_task = None
        try:
            conn.send(reply)
        except (EOFError, OSError):
            return
        except Exception as exc:  # unpicklable result
            conn.send(("error", task_id, _error_payload(exc)))


# ---------------------------------------------------------------- parent side


@dataclass(frozen=True)
class EngineSpec:
    """How to build an engine inside a worker: ``factory`` is ``"module:callable"``."""

    factory: str
    kwargs: Mapping[str, Any] = field(default_factory=dict)
    start_timeout_s: float = DEFAULT_START_TIMEOUT_S


@dataclass
class _Generation:
    """One worker process and the pipe and reader thread that go with it."""

    number: int
    proc: multiprocessing.process.BaseProcess
    conn: Connection
    reader: threading.Thread | None = None
    ready: asyncio.Future[int] | None = None
    dead: bool = False


class EngineWorker:
    """One engine class served by one long-lived spawned process.

    Calls are serialised (the engine holds one model). Must be used from a single
    asyncio loop.
    """

    def __init__(self, name: str, spec: EngineSpec) -> None:
        self.name = name
        self.spec = spec
        self.restarts = 0
        self._ctx = multiprocessing.get_context("spawn")
        self._gen: _Generation | None = None
        self._gen_counter = itertools.count(1)
        self._task_ids = itertools.count(1)
        self._pending: dict[int, asyncio.Future[Any]] = {}
        self._progress: dict[int, ProgressFn] = {}
        self._call_lock = asyncio.Lock()
        self._start_lock = asyncio.Lock()
        self._respawn_task: asyncio.Task[None] | None = None
        self._closed = False

    @property
    def pid(self) -> int | None:
        g = self._gen
        return g.proc.pid if g is not None and not g.dead else None

    @property
    def alive(self) -> bool:
        g = self._gen
        return g is not None and not g.dead and g.proc.is_alive()

    async def start(self) -> None:
        """Start the process if needed and wait until the engine is built."""
        if self._closed:
            raise WorkerError(f"worker {self.name} is closed")
        async with self._start_lock:
            g = self._gen
            if g is None or g.dead:
                g = await self._spawn()
            await self._await_ready(g)

    async def _spawn(self) -> _Generation:
        loop = asyncio.get_running_loop()
        parent_conn, child_conn = self._ctx.Pipe(duplex=True)
        proc = self._ctx.Process(
            target=_worker_main,
            args=(child_conn, self.spec.factory, dict(self.spec.kwargs)),
            name=f"videoflow-worker-{self.name}",
            daemon=True,
        )
        await asyncio.to_thread(proc.start)
        # Drop our copy of the child's end so the reader sees EOF when the child dies.
        child_conn.close()
        g = _Generation(next(self._gen_counter), proc, parent_conn)
        g.ready = loop.create_future()
        g.reader = threading.Thread(
            target=self._reader, args=(g, loop), name=f"{proc.name}-reader", daemon=True
        )
        self._gen = g
        g.reader.start()
        return g

    async def _await_ready(self, g: _Generation) -> None:
        assert g.ready is not None
        try:
            await asyncio.wait_for(asyncio.shield(g.ready), self.spec.start_timeout_s)
        except asyncio.CancelledError:
            # Cancellation can happen while the factory downloads/loads a model,
            # before call() reaches its running-task cancellation handler.
            await asyncio.shield(self._kill(g))
            raise
        except TimeoutError:
            await self._kill(g)
            raise WorkerStartError(f"worker {self.name} did not start in time") from None
        except WorkerError:
            await self._kill(g)
            raise

    def _reader(self, g: _Generation, loop: asyncio.AbstractEventLoop) -> None:
        while True:
            try:
                msg = g.conn.recv()
            except (EOFError, OSError):
                break
            except Exception as exc:  # undecodable payload
                msg = ("reader_error", None, _error_payload(exc))
            try:
                loop.call_soon_threadsafe(self._dispatch, g, msg)
            except RuntimeError:  # loop closed
                return
        with contextlib.suppress(RuntimeError):
            loop.call_soon_threadsafe(self._on_exit, g)

    def _dispatch(self, g: _Generation, msg: tuple[Any, ...]) -> None:
        kind, task_id, *rest = msg
        if kind == "ready":
            if g.ready is not None and not g.ready.done():
                g.ready.set_result(int(task_id))
            return
        if kind == "failed":
            exc_type, message, tb = rest[0]
            if g.ready is not None and not g.ready.done():
                g.ready.set_exception(
                    WorkerStartError(f"worker {self.name} failed to start: {exc_type}: {message}")
                )
                g.ready.exception()  # mark retrieved
            return
        if g is not self._gen:
            return  # stale message from a killed generation
        if kind == "progress":
            cb = self._progress.get(task_id)
            if cb is not None:
                res = cb(rest[0], rest[1])
                if asyncio.iscoroutine(res):
                    asyncio.ensure_future(res)
            return
        fut = self._pending.get(task_id)
        if fut is None or fut.done():
            return
        if kind == "result":
            fut.set_result(rest[0])
        elif kind in ("error", "reader_error"):
            fut.set_exception(WorkerTaskError(*rest[0]))

    def _on_exit(self, g: _Generation) -> None:
        g.dead = True
        if g.ready is not None and not g.ready.done():
            g.ready.set_exception(WorkerStartError(f"worker {self.name} exited during start"))
            g.ready.exception()
        if g is self._gen:
            for fut in self._pending.values():
                if not fut.done():
                    fut.set_exception(WorkerCrashedError(f"worker {self.name} died"))

    async def call(
        self,
        method: str,
        *args: Any,
        on_progress: ProgressFn | None = None,
        **kwargs: Any,
    ) -> Any:
        """Run ``engine.method(*args, **kwargs)`` in the worker and return its result.

        Cancelling the awaiting task kills the worker and respawns it in the background.
        """
        async with self._call_lock:
            await self.start()
            g = self._gen
            assert g is not None
            loop = asyncio.get_running_loop()
            task_id = next(self._task_ids)
            fut: asyncio.Future[Any] = loop.create_future()
            self._pending[task_id] = fut
            if on_progress is not None:
                self._progress[task_id] = on_progress
            try:
                await asyncio.to_thread(g.conn.send, ("call", task_id, method, args, kwargs))
                return await fut
            except asyncio.CancelledError:
                await asyncio.shield(self._kill(g))
                self._schedule_respawn()
                raise
            except WorkerCrashedError:
                await self._kill(g)
                self._schedule_respawn()
                raise
            except (BrokenPipeError, EOFError, OSError) as exc:
                await self._kill(g)
                self._schedule_respawn()
                raise WorkerCrashedError(f"worker {self.name} pipe closed") from exc
            finally:
                self._pending.pop(task_id, None)
                self._progress.pop(task_id, None)

    def _schedule_respawn(self) -> None:
        if self._closed:
            return
        self.restarts += 1

        async def respawn() -> None:
            await self.start()

        self._respawn_task = asyncio.ensure_future(respawn())
        self._respawn_task.add_done_callback(_consume_exception)

    async def _kill(self, g: _Generation) -> None:
        g.dead = True
        if self._gen is g:
            self._gen = None
        proc = g.proc
        if proc.is_alive():
            proc.kill()  # SIGKILL on POSIX, TerminateProcess on Windows
        # Closing first releases an overlapped Windows pipe read even when the
        # child was killed before it completed its engine factory.
        g.conn.close()
        await asyncio.to_thread(proc.join, KILL_JOIN_S)
        if g.reader is not None:
            await asyncio.to_thread(g.reader.join, 0.2)
        with contextlib.suppress(ValueError):
            proc.close()

    async def restart(self) -> None:
        """Kill the current process (if any) and start a new one."""
        if self._gen is not None:
            await self._kill(self._gen)
            self.restarts += 1
        await self.start()

    async def aclose(self) -> None:
        """Stop the worker: polite stop message, then kill after a grace period."""
        self._closed = True
        if self._respawn_task is not None and not self._respawn_task.done():
            self._respawn_task.cancel()
            with contextlib.suppress(BaseException):
                await self._respawn_task
        g = self._gen
        if g is None:
            return
        with contextlib.suppress(OSError, ValueError):
            g.conn.send(("stop", None))
        await asyncio.to_thread(g.proc.join, STOP_GRACE_S)
        await self._kill(g)


def _consume_exception(task: asyncio.Future[Any]) -> None:
    if not task.cancelled():
        task.exception()


class WorkerPool:
    """Engine workers by engine class name (``vad``, ``asr``, ``text_embed``, ...).

    Workers start lazily on first call and live until :meth:`aclose`.
    """

    def __init__(self, specs: Mapping[str, EngineSpec] | None = None) -> None:
        self._specs: dict[str, EngineSpec] = dict(specs or {})
        self._workers: dict[str, EngineWorker] = {}

    def register(self, name: str, spec: EngineSpec) -> None:
        if name in self._workers:
            raise ValueError(f"worker {name!r} already running")
        self._specs[name] = spec

    def worker(self, name: str) -> EngineWorker:
        w = self._workers.get(name)
        if w is None:
            try:
                spec = self._specs[name]
            except KeyError:
                raise KeyError(f"no engine registered as {name!r}") from None
            w = self._workers[name] = EngineWorker(name, spec)
        return w

    async def call(
        self,
        name: str,
        method: str,
        *args: Any,
        on_progress: ProgressFn | None = None,
        **kwargs: Any,
    ) -> Any:
        return await self.worker(name).call(method, *args, on_progress=on_progress, **kwargs)

    async def aclose(self) -> None:
        workers, self._workers = list(self._workers.values()), {}
        await asyncio.gather(*(w.aclose() for w in workers), return_exceptions=True)
