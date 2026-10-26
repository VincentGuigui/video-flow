import multiprocessing
import runpy
import sys
import types
from pathlib import Path


def test_windowed_workers_have_log_streams_before_freeze_support(monkeypatch, tmp_path):
    events = []

    def freeze_support():
        assert sys.stdout is not None and sys.stderr is not None
        events.append("worker setup")

    cli = types.ModuleType("videoflow.cli")
    cli.app = lambda: events.append("application")
    monkeypatch.setitem(sys.modules, "videoflow.cli", cli)
    monkeypatch.setattr(multiprocessing, "freeze_support", freeze_support)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    entry = Path(__file__).parents[2] / "videoflow" / "desktop_entry.py"
    with monkeypatch.context() as context:
        context.setattr(sys, "stdout", None)
        context.setattr(sys, "stderr", None)
        result = runpy.run_path(str(entry), run_name="__main__")
        stream = result["stream"]
    stream.close()
    assert events == ["worker setup", "application"]
    assert (tmp_path / "Video-Flow" / "logs" / "desktop.log").exists()
