from __future__ import annotations

import numpy as np

from videoflow.engines.vad import silero_onnx as sv


def test_hysteresis_merge_filter_and_pad():
    w = 0.032
    probs = np.zeros(100, dtype=np.float32)
    probs[10:40] = 0.9  # 0.96 s
    probs[40:43] = 0.4  # dip above the off threshold keeps the segment open
    probs[43:50] = 0.9
    probs[60:62] = 0.9  # 64 ms blip, dropped
    probs[80:100] = 0.9  # runs to the end
    spans = sv.probs_to_ranges(probs, window_s=w, total_s=3.2)
    assert len(spans) == 2
    assert np.allclose(spans[0], (10 * w - 0.03, 50 * w + 0.03), atol=w)
    assert spans[1][1] == 3.2


def test_close_segments_are_merged():
    w = 0.032
    probs = np.zeros(60, dtype=np.float32)
    probs[5:20] = 0.9
    probs[22:40] = 0.9  # 2 windows (64 ms) of silence < min_silence 100 ms
    assert len(sv.probs_to_ranges(probs, window_s=w, total_s=2.0)) == 1


class FakeSession:
    def __init__(self, loud_from: int):
        self.loud_from = loud_from
        self.calls = 0
        self.shapes = set()

    def run(self, _outputs, feeds):
        self.shapes.add((feeds["input"].shape, feeds["state"].shape, int(feeds["sr"])))
        prob = 0.95 if self.calls >= self.loud_from else 0.01
        self.calls += 1
        return [np.array([[prob]], dtype=np.float32), feeds["state"]]


def make(session):
    vad = sv.SileroVad.__new__(sv.SileroVad)
    vad._session = session
    vad.threshold = 0.5
    return vad


def test_windowing_context_and_ranges():
    sess = FakeSession(loud_from=20)
    vad = make(sess)
    audio = np.zeros(16_000 * 2, dtype=np.float32)
    ranges = vad.speech_ranges(audio, 16_000)
    assert sess.shapes == {((1, sv.CONTEXT + sv.WINDOW), (2, 1, 128), 16_000)}
    assert sess.calls == 63  # 32000 / 512 rounded up
    assert len(ranges) == 1
    assert abs(ranges[0].start_us - (20 * 512 / 16_000 - 0.03) * 1e6) < 1000
    assert ranges[0].end_us == 2_000_000


def test_resamples_other_rates():
    sess = FakeSession(loud_from=10**9)
    vad = make(sess)
    assert vad.speech_ranges(np.zeros(48_000, dtype=np.float32), 48_000) == []
    assert sess.calls == 32  # 1 s at 16 kHz


def test_empty_audio():
    assert make(FakeSession(0)).speech_ranges(np.zeros(0, dtype=np.float32), 16_000) == []
