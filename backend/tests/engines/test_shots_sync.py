"""Model-free adapters on synthetic media: PySceneDetect shots and GCC-PHAT sync."""

from __future__ import annotations

import numpy as np
import pytest

from tests.engines.conftest import decode_audio
from videoflow.analysis import sync_gccphat as sync

SR = 8000


# --------------------------------------------------------------------------- shots


def test_scenedetect_finds_all_cuts(samples_dir, samples_manifest):
    pytest.importorskip("scenedetect")
    from videoflow.analysis.shots import SceneDetectShots

    cuts = samples_manifest["cuts"]
    shots = SceneDetectShots().detect(samples_dir / cuts["file"], "ast_test")
    assert len(shots) == len(cuts["cut_times_s"]) + 1  # 3 of 3 cuts
    found = [s.start_us / 1e6 for s in shots[1:]]
    for want, got in zip(cuts["cut_times_s"], found, strict=True):
        assert abs(want - got) <= 1 / 24 + 1e-3
    assert shots[0].start_us == 0
    assert all(a.end_us == b.start_us for a, b in zip(shots, shots[1:], strict=False))
    assert [s.index for s in shots] == [0, 1, 2, 3]
    assert len({s.id for s in shots}) == 4 and shots[0].asset_id == "ast_test"


def test_scenedetect_single_shot_covers_clip(samples_dir, samples_manifest):
    pytest.importorskip("scenedetect")
    from videoflow.analysis.shots import SceneDetectShots

    name = "broll_a1.mp4"
    shots = SceneDetectShots().detect(samples_dir / name, "a")
    assert len(shots) == 1
    want = samples_manifest["files"][name]["duration_s"]
    assert shots[0].start_us == 0 and abs(shots[0].end_us / 1e6 - want) < 0.05


# --------------------------------------------------------------------------- sync


def speech_like(seconds: float, seed: int, sr: int = SR) -> np.ndarray:
    """Noise bursts with irregular on/off times (a stand-in for speech onsets)."""
    rng = np.random.default_rng(seed)
    x = np.zeros(int(seconds * sr))
    t = 0.3
    while t < seconds - 0.6:
        dur = rng.uniform(0.08, 0.5)
        n = int(dur * sr)
        i = int(t * sr)
        x[i : i + n] += rng.standard_normal(n) * np.hanning(n) * rng.uniform(0.3, 1.0)
        t += dur + rng.uniform(0.05, 0.6)
    return x


def delayed(x: np.ndarray, lag_s: float, sr: int = SR, noise=0.02, seed=5) -> np.ndarray:
    pad = int(round(lag_s * sr))
    y = np.concatenate([np.zeros(pad), x])
    return y + np.random.default_rng(seed).standard_normal(len(y)) * noise


def test_recovers_known_lag_and_sign():
    a = speech_like(20, 1)
    b = delayed(a, 3.217)
    r = sync.estimate_sync(a, b, SR, asset_a="A", asset_b="B")
    assert r.accepted and r.psr >= sync.PSR_ACCEPT
    assert r.offset_us == pytest.approx(-3_217_000, abs=2_000)  # b time + offset = a time
    assert (r.asset_a, r.asset_b) == ("A", "B")
    # swapping the roles flips the sign
    r2 = sync.estimate_sync(b, a, SR)
    assert r2.offset_us == pytest.approx(3_217_000, abs=2_000)


def test_unrelated_and_shuffled_controls_are_rejected():
    a = speech_like(20, 1)
    b = delayed(a, 3.0)
    rng = np.random.default_rng(0)
    other = sync.estimate_sync(a, speech_like(20, 99), SR)
    assert not other.accepted and other.psr < 2
    env_a, env_b = sync.onset_envelope(a, SR), sync.onset_envelope(b, SR)
    for _ in range(10):
        shuffled = sync.coarse_lag(env_a, rng.permutation(env_b))
        assert shuffled.psr < 2
    assert sync.coarse_lag(env_a, env_b).psr >= sync.PSR_ACCEPT


def test_band_limited_and_gain_changed_copy_still_syncs():
    from scipy.signal import butter, sosfilt

    a = speech_like(20, 7)
    b = sosfilt(butter(4, [250, 3000], btype="band", fs=SR, output="sos"), delayed(a, 1.5)) * 0.3
    r = sync.estimate_sync(a, b, SR)
    assert r.accepted and r.offset_us == pytest.approx(-1_500_000, abs=3_000)


def test_drift_is_estimated():
    a = speech_like(90, 3)
    ppm = 300.0
    # B's clock runs 300 ppm slow: its samples are stretched by (1 + ppm*1e-6).
    b = delayed(_stretch(a, 1 + ppm * 1e-6), 2.0)
    r = sync.estimate_sync(a, b, SR)
    assert r.accepted
    assert r.drift_ppm == pytest.approx(ppm, abs=120)
    assert r.offset_us == pytest.approx(-2_000_000, abs=15_000)  # offset at A time 0


def _stretch(x: np.ndarray, factor: float) -> np.ndarray:
    idx = np.arange(int(len(x) * factor)) / factor
    return np.interp(idx, np.arange(len(x)), x)


def test_no_overlap_inputs_do_not_crash():
    r = sync.estimate_sync(np.zeros(100), np.zeros(100), SR)
    assert not r.accepted and r.psr == 0.0


def test_sample_pair_lag_3217(samples_dir, samples_manifest):
    ref = samples_manifest["sync"]
    a = decode_audio(samples_dir / ref["reference"], SR).astype(float)
    b = decode_audio(samples_dir / ref["other"], SR).astype(float)
    r = sync.estimate_sync(a, b, SR)
    assert r.accepted and r.psr >= 4
    assert -r.offset_us / 1e6 == pytest.approx(ref["lag_s"], abs=0.01)


def test_sample_unrelated_control_psr_below_two(samples_dir, samples_manifest):
    ref = samples_manifest["sync"]
    a = decode_audio(samples_dir / ref["reference"], SR).astype(float)
    other = decode_audio(samples_dir / "retake_en.mp4", SR).astype(float)
    r = sync.estimate_sync(a, other, SR)
    assert r.psr < 2 and not r.accepted
