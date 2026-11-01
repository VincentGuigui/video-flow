"""Desktop startup: the timeline log and the backend that starts beside the window."""

import socket

import pytest

from videoflow.desktop import startup


def test_timeline_is_reported_once_in_order(monkeypatch, capsys):
    monkeypatch.setattr(startup, "_marks", [])
    monkeypatch.setattr(startup, "_reported", False)
    startup.mark("window")
    startup.mark("editor")
    labels = [label for label, _ in startup.marks()]
    times = [seconds for _, seconds in startup.marks()]
    assert labels == ["python", "window", "editor"] and times == sorted(times)
    line = startup.report()
    assert line and "window" in line and line in capsys.readouterr().err
    assert startup.report() is None


def test_backend_starts_without_blocking_and_closes(tmp_path):
    pytest.importorskip("PySide6.QtWebEngineWidgets")  # needs the desktop extra and Qt libraries
    from videoflow.desktop.host import Backend
    from videoflow.project.models import new_project
    from videoflow.project.store import Bundle

    bundle = Bundle.create(tmp_path / "edit.video-flow", new_project("Startup"))
    with socket.socket() as candidate:
        candidate.bind(("127.0.0.1", 0))
        port = candidate.getsockname()[1]
    backend = Backend(bundle, port, None)
    assert not backend.ready and backend.server is None  # nothing built before the thread runs
    backend.start()
    backend.wait()
    assert backend.ready
    backend.close()
    assert not backend.thread.is_alive()
