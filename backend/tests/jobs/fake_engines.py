"""Engines used by worker tests. Imported by path inside spawned worker processes."""

from __future__ import annotations

import os
import time
from typing import Any

from videoflow.jobs.workers import report_progress


class SleepyEngine:
    def __init__(self, fail: bool = False, tag: str = "") -> None:
        if fail:
            raise RuntimeError("engine init failed")
        self.tag = tag

    def pid(self) -> int:
        return os.getpid()

    def echo(self, value: Any, suffix: str = "") -> Any:
        return f"{value}{suffix}" if suffix else value

    def sleep(self, seconds: float, steps: int = 10) -> str:
        for i in range(steps):
            time.sleep(seconds / steps)
            report_progress((i + 1) / steps, f"step {i + 1}")
        return "slept"

    def fail(self) -> None:
        raise ValueError("bad input")

    def crash(self) -> None:
        os._exit(3)

    def unpicklable(self) -> Any:
        return lambda: 1
