from __future__ import annotations

import json
import subprocess
from fractions import Fraction
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from scipy.signal import correlate

from videoflow import samples
from videoflow.media.caps import locate_binaries


def _probe(path: Path) -> dict[str, Any]:
    out = subprocess.run(
        [str(locate_binaries().ffprobe), "-v", "error", "-print_format", "json",
         "-show_format", "-show_streams", str(path)],
        capture_output=True, text=True, check=True,
    ).stdout  # fmt: skip
    return json.loads(out)


def _decode(path: Path, rate: int = 8000) -> np.ndarray:
    raw = subprocess.run(
        [str(locate_binaries().ffmpeg), "-v", "error", "-i", str(path), "-vn", "-ac", "1",
         "-ar", str(rate), "-f", "f32le", "-"],
        capture_output=True, check=True,
    ).stdout  # fmt: skip
    return np.frombuffer(raw, dtype="<f4")


def _fraction(text: str) -> Fraction:
    return Fraction(text)


def test_manifest_lists_every_file(samples_dir: Path, samples_manifest: dict[str, Any]) -> None:
    files = samples_manifest["files"]
    assert samples_manifest["generator_hash"] == samples.generator_hash()
    on_disk = {p.name for p in samples_dir.glob("*.mp4")}
    assert on_disk == set(files)
    assert not (samples_dir / "_work").exists()


def test_probe_matches_manifest(samples_dir: Path, samples_manifest: dict[str, Any]) -> None:
    for name, exp in samples_manifest["files"].items():
        info = _probe(samples_dir / name)
        v = next(s for s in info["streams"] if s["codec_type"] == "video")
        audio = [s for s in info["streams"] if s["codec_type"] == "audio"]
        assert (v["width"], v["height"]) == (exp["width"], exp["height"]), name
        assert int(v["nb_frames"]) == exp["frames"], name
        if exp["vfr"]:
            assert _fraction(v["avg_frame_rate"]) != _fraction(v["r_frame_rate"]), name
        else:
            assert _fraction(v["avg_frame_rate"]) == _fraction(exp["fps"]), name
        if exp["audio_channels"]:
            assert len(audio) == 1 and audio[0]["channels"] == exp["audio_channels"], name
            assert abs(float(audio[0]["duration"]) - exp["duration_s"]) < 0.1, name
        else:
            assert audio == [], name
        if exp["color_trc"]:
            assert v["color_transfer"] == exp["color_trc"], name
            assert v["color_primaries"] == "bt2020", name


def test_required_variants_exist(samples_manifest: dict[str, Any]) -> None:
    f = samples_manifest["files"]
    shapes = {(e["width"], e["height"], e["fps"], e["audio_channels"]) for e in f.values()}
    assert (1280, 720, "25/1", 2) in shapes
    assert (854, 480, "30000/1001", 1) in shapes
    assert (1080, 1920, "24/1", 0) in shapes
    assert any(e["vfr"] for e in f.values())
    assert any(e["color_trc"] == "arib-std-b67" for e in f.values())


@pytest.mark.parametrize("lang", ["fr", "en"])
def test_retake_ground_truth(samples_manifest: dict[str, Any], lang: str) -> None:
    script = samples_manifest["retake_scripts"][lang]
    utts = script["utterances"]
    assert [u["kind"] for u in utts] == ["false_start", "take", "take", "take"]
    for prev, nxt in zip(utts, utts[1:], strict=False):
        assert nxt["start_s"] - prev["end_s"] == pytest.approx(script["gap_s"], abs=1e-3)
    assert script["retake_groups"] == [[f"{lang}-t1", f"{lang}-t2", f"{lang}-t3"]]
    assert len(script["expected_beats"]) == 1
    assert utts[-1]["end_s"] < samples_manifest["files"][script["file"]]["duration_s"]


@pytest.mark.parametrize("lang", ["fr", "en"])
def test_retake_audio_has_speech_then_gaps(
    samples_dir: Path, samples_manifest: dict[str, Any], lang: str
) -> None:
    script = samples_manifest["retake_scripts"][lang]
    x = _decode(samples_dir / script["file"])
    rate = 8000

    def rms(a: float, b: float) -> float:
        return float(np.sqrt(np.mean(x[int(a * rate) : int(b * rate)] ** 2)))

    for u in script["utterances"]:
        assert rms(u["start_s"] + 0.05, u["end_s"] - 0.05) > 0.01
    for prev, nxt in zip(script["utterances"], script["utterances"][1:], strict=False):
        assert rms(prev["end_s"] + 0.15, nxt["start_s"] - 0.15) < 0.002


def test_sync_lag_recoverable(samples_dir: Path, samples_manifest: dict[str, Any]) -> None:
    sync = samples_manifest["sync"]
    assert sync["lag_s"] == 3.217
    rate = 8000
    a = _decode(samples_dir / sync["reference"], rate)
    b = _decode(samples_dir / sync["other"], rate)
    corr = correlate(b, a, mode="full", method="fft")
    lag = (int(np.argmax(corr)) - (len(a) - 1)) / rate
    assert lag == pytest.approx(sync["lag_s"], abs=0.01)


def test_silent_and_broll(samples_dir: Path, samples_manifest: dict[str, Any]) -> None:
    silent = [n for n, e in samples_manifest["files"].items() if e["audio_channels"]]
    assert "clip_silent.mp4" in samples_manifest["silent_files"]
    assert float(np.max(np.abs(_decode(samples_dir / "clip_silent.mp4")))) == 0.0
    group = samples_manifest["near_duplicate_groups"][0]
    assert len(group) == 2 and all(n in samples_manifest["files"] for n in group)
    assert samples_manifest["different_shots"]
    assert silent  # sanity: non-silent clips exist
    assert len(samples_manifest["cuts"]["cut_times_s"]) == 3


def test_ensure_samples_uses_cache(
    samples_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("VIDEOFLOW_SAMPLES_CACHE", str(samples_dir.parent))
    assert samples.ensure_samples() == samples_dir
    assert samples_dir.name == samples.generator_hash()


def test_generation_is_fast_and_deterministic(tmp_path: Path) -> None:
    import hashlib
    import time

    t0 = time.monotonic()
    samples.generate(tmp_path / "a")
    assert time.monotonic() - t0 < 30
    samples.generate(tmp_path / "b")
    for p in sorted((tmp_path / "a").iterdir()):
        digest = [hashlib.sha256(q.read_bytes()).hexdigest() for q in (p, tmp_path / "b" / p.name)]
        assert digest[0] == digest[1], p.name
