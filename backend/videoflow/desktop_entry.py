"""Frozen application entry point; no Node, uv or development server at runtime."""

import multiprocessing
import os
import sys
from pathlib import Path

if __name__ == "__main__":
    # Spawned frozen workers enter freeze_support before the CLI. Configure their
    # streams first as well: Hub progress bars and inference libraries write here.
    if sys.stdout is None or sys.stderr is None:
        logs = Path(os.environ.get("LOCALAPPDATA", Path.home() / ".local" / "share"))
        logs = logs / "Video-Flow" / "logs"
        logs.mkdir(parents=True, exist_ok=True)
        stream = (logs / "desktop.log").open("a", encoding="utf-8", buffering=1)
        sys.stdout = stream
        sys.stderr = stream
    multiprocessing.freeze_support()
    from videoflow.cli import app

    app()
