"""FFmpeg capabilities are probed once per build and kept between launches."""

import pytest

from videoflow.media import caps
from videoflow.media.caps import FFmpegBinaries, FFmpegCaps


@pytest.fixture
def fake_build(tmp_path, monkeypatch):
    binaries = FFmpegBinaries(tmp_path / "ffmpeg", tmp_path / "ffprobe")
    for path in (binaries.ffmpeg, binaries.ffprobe):
        path.write_bytes(b"build")
    probes = []

    def probe(found):
        probes.append(found)
        return FFmpegCaps(
            ffmpeg=found.ffmpeg,
            ffprobe=found.ffprobe,
            version="7.1.1",
            version_tuple=(7, 1, 1),
            graph_flag=caps.GRAPH_FLAG_NEW,
            filters=frozenset({"xfade", "zscale"}),
            encoders=frozenset({"libx264"}),
        )

    monkeypatch.setattr(caps, "locate_binaries", lambda: binaries)
    monkeypatch.setattr(caps, "probe_caps", probe)
    monkeypatch.setattr(caps, "caps_cache_file", lambda: tmp_path / "ffmpeg-caps.json")
    monkeypatch.setattr(caps, "_cached", None)
    monkeypatch.setattr(caps, "_cached_fingerprint", None)
    return binaries, probes


def _new_process(monkeypatch):
    monkeypatch.setattr(caps, "_cached", None)
    monkeypatch.setattr(caps, "_cached_fingerprint", None)


def test_probe_runs_once_per_build_across_launches(fake_build, monkeypatch, tmp_path):
    binaries, probes = fake_build
    first = caps.get_caps()
    assert len(probes) == 1 and (tmp_path / "ffmpeg-caps.json").is_file()
    _new_process(monkeypatch)
    again = caps.get_caps()
    assert len(probes) == 1 and again == first and again.has_filter("zscale")
    caps.get_caps(refresh=True)  # the binaries are unchanged: no probe
    assert len(probes) == 1


def test_a_changed_build_or_a_damaged_cache_is_probed_again(fake_build, monkeypatch, tmp_path):
    binaries, probes = fake_build
    caps.get_caps()
    binaries.ffmpeg.write_bytes(b"a newer build")
    caps.get_caps(refresh=True)
    assert len(probes) == 2
    (tmp_path / "ffmpeg-caps.json").write_text("{broken", encoding="utf-8")
    _new_process(monkeypatch)
    caps.get_caps()
    assert len(probes) == 3
