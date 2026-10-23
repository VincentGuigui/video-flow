import json
import shutil

import pytest

from videoflow.hw import ai
from videoflow.hw.report import build_report, format_report


def test_report_without_ffmpeg(monkeypatch, tmp_path):
    monkeypatch.setattr(ai, "_import_ort", lambda: None)
    r = build_report(ffmpeg=tmp_path / "missing")
    assert "error" in r["ffmpeg"] and r["video"] is None and r["ai"]["selected"] is None
    assert "NOT FOUND" in format_report(r) and "not installed" in format_report(r)


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
def test_report_real():
    r = build_report()
    json.dumps(r)
    assert r["ffmpeg"]["version"] and r["video"]["encoder"]
    assert "FFmpeg:" in format_report(r)
