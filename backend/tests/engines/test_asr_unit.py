from __future__ import annotations

import sys
import types
from types import SimpleNamespace

import numpy as np
import pytest

from videoflow.core.time import TimeRange
from videoflow.engines.asr import parakeet_onnx as pk
from videoflow.engines.asr.chunks import plan_chunks

SR = 16_000


def test_tokens_merge_into_words_with_end_at_next_start():
    tokens = [" To", "day", " we", " are", " go", "ing"]
    times = [0.32, 0.48, 0.64, 0.88, 1.04, 1.20]
    words = pk.tokens_to_words(tokens, times)
    assert [w.text for w in words] == ["Today", "we", "are", "going"]
    assert [w.start_us for w in words] == [320_000, 640_000, 880_000, 1_040_000]
    assert [w.end_us for w in words[:3]] == [640_000, 880_000, 1_040_000]
    assert all(w.prob is None for w in words)
    assert words[-1].end_us == 1_200_000 + pk.MAX_TAIL_US  # last word: tail cap


def test_word_end_is_capped_by_range_and_tail():
    words = pk.tokens_to_words(
        [" a", " b"], [0.0, 1.8], offset_us=1_000_000, end_cap_us=1_000_000 + 2_000_000
    )
    assert words[0].end_us == 1_000_000 + pk.MAX_TAIL_US  # not stretched over the 1.8 s gap
    assert words[1].start_us == 2_800_000
    assert words[1].end_us == 3_000_000  # capped by the chunk / VAD range end


def test_first_token_without_space_starts_a_word():
    words = pk.tokens_to_words(["Hel", "lo"], [0.0, 0.1])
    assert [w.text for w in words] == ["Hello"]


def test_plan_chunks_whole_and_ranges():
    assert plan_chunks(10 * SR, SR, None) == [(0, 10 * SR)]
    spans = plan_chunks(20 * SR, SR, [TimeRange(start_us=2_000_000, end_us=3_000_000)])
    assert spans == [(int(1.7 * SR), int(3.3 * SR))]  # 0.3 s padding


def test_plan_chunks_merges_close_ranges_and_clamps():
    rs = [
        TimeRange(start_us=0, end_us=1_000_000),
        TimeRange(start_us=1_800_000, end_us=2_000_000),
        TimeRange(start_us=9_000_000, end_us=9_900_000),
    ]
    spans = plan_chunks(10 * SR, SR, rs)
    assert spans == [(0, int(2.3 * SR)), (int(8.7 * SR), 10 * SR)]


def test_plan_chunks_cuts_long_spans_at_quiet_points():
    audio = np.ones(70 * SR, dtype=np.float32)
    audio[29 * SR + 5000 : 29 * SR + 6000] = 0.0  # a quiet gap just before the 30 s limit
    spans = plan_chunks(len(audio), SR, None, audio=audio, max_s=30.0)
    assert spans[0][1] // 1000 == (29 * SR + 5500) // 1000
    assert spans[0][0] == 0 and spans[-1][1] == len(audio)
    assert all(b - a <= 30 * SR for a, b in spans)
    assert all(spans[i][1] == spans[i + 1][0] for i in range(len(spans) - 1))


def test_parakeet_routes_sessions_through_make_session(monkeypatch):
    pytest.importorskip("onnx_asr")  # `ml` extra
    from onnx_asr.models import nemo

    calls = []

    def fake_make(path, prefer="auto", **kw):
        calls.append((str(path), prefer))
        return SimpleNamespace(session=f"sess:{path}", device=pk.Device.CPU)

    monkeypatch.setattr(pk, "make_session", fake_make)
    real = nemo.rt
    devices: dict = {}
    with pk._routed_sessions("gpu", devices):
        enc = nemo.rt.InferenceSession("m/encoder-model.int8.onnx", providers=["X"])
        dec = nemo.rt.InferenceSession("m/decoder_joint-model.int8.onnx")
        assert nemo.rt.SessionOptions  # the rest of onnxruntime stays reachable
    assert nemo.rt is real
    assert enc == "sess:m/encoder-model.int8.onnx" and dec.startswith("sess:")
    assert calls == [
        ("m/encoder-model.int8.onnx", "gpu"),
        ("m/decoder_joint-model.int8.onnx", "cpu"),  # decoder loop pinned to the CPU
    ]
    assert set(devices) == {"encoder", "decoder"}


def test_parakeet_transcribe_offsets_and_ranges():
    eng = pk.ParakeetOnnxAsr.__new__(pk.ParakeetOnnxAsr)
    eng.max_chunk_s = 30.0
    eng.info = pk.EngineInfo(engine_id="x", model_id="y")
    seen = []

    def rec(chunk):
        seen.append(len(chunk))
        return [" hi", " you"], [0.1, 0.5]

    eng._recognize = rec
    audio = np.zeros(10 * SR, dtype=np.float32)
    tr = eng.transcribe(audio, SR, "en", [TimeRange(start_us=4_000_000, end_us=5_000_000)])
    assert seen == [int(1.6 * SR)]
    assert [w.text for w in tr.words] == ["hi", "you"]
    assert tr.words[0].start_us == 3_700_000 + 100_000
    assert tr.words[1].end_us <= 5_300_000  # capped by the padded range
    assert tr.language == "en"
    with pytest.raises(ValueError):
        eng.transcribe(audio, 8000)


def fake_faster_whisper(monkeypatch, record):
    class Model:
        def __init__(self, path, device, compute_type):
            record["init"] = (path, device, compute_type)

        def transcribe(self, audio, **kw):
            record.setdefault("calls", []).append((audio.dtype, kw))
            w = lambda t, s, e, p: SimpleNamespace(word=t, start=s, end=e, probability=p)  # noqa: E731
            seg = SimpleNamespace(words=[w(" Hello,", 0.0, 0.4, 0.9), w(" ", 0.4, 0.5, 0.1)])
            return iter([seg]), SimpleNamespace(language="en")

    mod = types.ModuleType("faster_whisper")
    mod.WhisperModel = Model
    monkeypatch.setitem(sys.modules, "faster_whisper", mod)


def test_faster_whisper_adapter(monkeypatch, tmp_path):
    from videoflow.engines.asr import faster_whisper as fw

    rec: dict = {}
    fake_faster_whisper(monkeypatch, rec)
    monkeypatch.setattr(fw, "cuda_available", lambda: False)
    eng = fw.FasterWhisperAsr(model_dir=tmp_path)
    assert rec["init"] == (str(tmp_path), "cpu", "int8")
    assert eng.info.device == "cpu"
    audio = np.zeros(3 * SR, dtype=np.float32)
    tr = eng.transcribe(audio, SR, None, [TimeRange(start_us=1_000_000, end_us=2_000_000)])
    assert [w.text for w in tr.words] == ["Hello,"]  # blank token dropped
    assert tr.words[0].prob == pytest.approx(0.9)
    assert tr.words[0].start_us == 700_000
    assert tr.language == "en"
    dtype, kw = rec["calls"][0]
    assert (
        dtype == np.float32 and kw["word_timestamps"] and kw["condition_on_previous_text"] is False
    )


def test_faster_whisper_uses_cuda_when_present_and_not_cpu_only(monkeypatch, tmp_path):
    from videoflow.engines.asr import faster_whisper as fw

    rec: dict = {}
    fake_faster_whisper(monkeypatch, rec)
    monkeypatch.setattr(fw, "cuda_available", lambda: True)
    fw.FasterWhisperAsr("auto", model_dir=tmp_path)
    assert rec["init"][1:] == ("cuda", "float16")
    fw.FasterWhisperAsr("cpu", model_dir=tmp_path)
    assert rec["init"][1:] == ("cpu", "int8")


def test_faster_whisper_missing_package(monkeypatch):
    from videoflow.engines.asr import faster_whisper as fw

    monkeypatch.setitem(sys.modules, "faster_whisper", None)
    with pytest.raises(RuntimeError, match="whisper"):
        fw.FasterWhisperAsr()
