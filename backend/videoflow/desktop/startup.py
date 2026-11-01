"""Startup timeline of the desktop app (docs/reference/desktop-runtime.md).

Each step of a launch is marked in seconds since the process started; when the editor
reports that it shows the project, one line goes to the log (stderr, which the packaged
app writes to logs/desktop.log). Importing this module is cheap: do it first.
"""

import os
import sys
import threading
import time

_ORIGIN = time.perf_counter()
_marks: list[tuple[str, float]] = []
_lock = threading.Lock()
_reported = False


def _process_age() -> float:
    """Seconds between the process start and this module's import (0 when unknown)."""
    try:
        if sys.platform == "win32":
            import ctypes
            from ctypes import wintypes

            created, ignored = wintypes.FILETIME(), wintypes.FILETIME()
            kernel = ctypes.windll.kernel32
            handle = kernel.GetCurrentProcess()
            if not kernel.GetProcessTimes(
                handle,
                ctypes.byref(created),
                ctypes.byref(ignored),
                ctypes.byref(ignored),
                ctypes.byref(ignored),
            ):
                return 0.0
            now = wintypes.FILETIME()
            kernel.GetSystemTimeAsFileTime(ctypes.byref(now))

            def ticks(value: wintypes.FILETIME) -> int:
                return (value.dwHighDateTime << 32) | value.dwLowDateTime

            return max(0.0, (ticks(now) - ticks(created)) / 10_000_000)
        if sys.platform.startswith("linux"):
            with open("/proc/self/stat", encoding="ascii") as stat:
                fields = stat.read().rsplit(")", 1)[1].split()
            started = int(fields[19]) / os.sysconf("SC_CLK_TCK")
            with open("/proc/uptime", encoding="ascii") as uptime:
                return max(0.0, float(uptime.read().split()[0]) - started)
    except (OSError, ValueError, AttributeError, IndexError):
        pass
    return 0.0


_BEFORE = _process_age()
"""Time spent before Python reached Video-Flow (bootloader, interpreter, DLLs)."""


def elapsed() -> float:
    return _BEFORE + time.perf_counter() - _ORIGIN


def mark(label: str) -> None:
    """Record that a step finished now (thread safe)."""
    with _lock:
        _marks.append((label, elapsed()))


def marks() -> list[tuple[str, float]]:
    with _lock:
        return [("python", _BEFORE), *_marks]


def summary() -> str:
    steps = ", ".join(f"{label} {seconds:.2f} s" for label, seconds in marks())
    return f"Video-Flow startup (seconds since the process started): {steps}"


def report() -> str | None:
    """Write the timeline once, when the editor is ready; later calls do nothing."""
    global _reported
    with _lock:
        if _reported:
            return None
        _reported = True
    line = summary()
    print(line, file=sys.stderr, flush=True)
    return line
