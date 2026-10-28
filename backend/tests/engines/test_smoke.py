"""Smoke tier: real CPU models (downloaded on first run) on the synthetic samples.

Run with ``uv run pytest -m smoke tests/engines``. Models come from the pinned manifest.
"""

from __future__ import annotations

import re

import numpy as np
import pytest

from tests.engines.conftest import decode_audio
from videoflow.engines.vision.frames import sample_frames

pytestmark = pytest.mark.smoke

SR = 16_000


@pytest.fixture(scope="module")
def en(samples_dir, samples_manifest):
    script = samples_manifest["retake_scripts"]["en"]
    return decode_audio(samples_dir / script["file"], SR), script


def overlap_us(a, b):
    return max(0, min(a[1], b[1]) - max(a[0], b[0]))


def test_silero_finds_flite_speech_ranges(en):
    pytest.importorskip("onnxruntime")
    from videoflow.engines.vad.silero_onnx import SileroVad

    audio, script = en
    vad = SileroVad("cpu")
    assert vad.info.device == "cpu"
    ranges = vad.speech_ranges(audio, SR)
    truth = [(u["start_s"] * 1e6, u["end_s"] * 1e6) for u in script["utterances"]]
    assert len(ranges) == len(truth)
    for r, t in zip(ranges, truth, strict=True):
        assert overlap_us((r.start_us, r.end_us), t) / (t[1] - t[0]) > 0.9
        assert abs(r.start_us - t[0]) < 300_000 and abs(r.end_us - t[1]) < 300_000


def test_silero_gives_nothing_on_silence(samples_dir):
    pytest.importorskip("onnxruntime")
    from videoflow.engines.vad.silero_onnx import SileroVad

    assert SileroVad("cpu").speech_ranges(np.zeros(SR * 3, dtype=np.float32), SR) == []


def words_text(tr):
    return " ".join(w.text.lower().strip(".,!?") for w in tr.words)


def check_retake_words(tr, script):
    assert tr.words
    assert all(w.end_us > w.start_us for w in tr.words)
    assert all(a.start_us <= b.start_us for a, b in zip(tr.words, tr.words[1:], strict=False))
    takes = [u for u in script["utterances"] if u["kind"] == "take"]
    text = words_text(tr)
    assert len(re.findall(r"assemble", text)) >= 2
    for u in takes:
        inside = [w for w in tr.words if u["start_s"] - 0.6 <= w.start_us / 1e6 <= u["end_s"] + 0.6]
        assert len(inside) >= 6, u["id"]
        assert "assemble" in " ".join(w.text.lower() for w in inside)


def test_parakeet_words_on_english_retakes(en):
    pytest.importorskip("onnx_asr")
    from videoflow.engines.asr.parakeet_onnx import ParakeetOnnxAsr

    audio, script = en
    asr = ParakeetOnnxAsr("cpu")
    assert asr.info.device == "cpu"
    tr = asr.transcribe(audio, SR, "en")
    check_retake_words(tr, script)
    assert all(w.prob is None for w in tr.words)
    assert tr.engine is not None and tr.engine.engine_id == "parakeet-onnx"


def test_parakeet_respects_vad_ranges(en):
    pytest.importorskip("onnx_asr")
    from videoflow.core.time import TimeRange
    from videoflow.engines.asr.parakeet_onnx import ParakeetOnnxAsr

    audio, script = en
    take = [u for u in script["utterances"] if u["kind"] == "take"][1]
    rng = TimeRange(start_us=int(take["start_s"] * 1e6), end_us=int(take["end_s"] * 1e6))
    tr = ParakeetOnnxAsr("cpu").transcribe(audio, SR, "en", [rng])
    assert tr.words
    assert all(
        rng.start_us - 400_000 <= w.start_us and w.end_us <= rng.end_us + 400_000 for w in tr.words
    )
    assert "assemble" in words_text(tr)


def test_parakeet_runs_on_french_sample(samples_dir, samples_manifest):
    """Only a run check: the flite voice is English, so French words are not asserted."""
    pytest.importorskip("onnx_asr")
    from videoflow.engines.asr.parakeet_onnx import ParakeetOnnxAsr

    script = samples_manifest["retake_scripts"]["fr"]
    audio = decode_audio(samples_dir / script["file"], SR)
    tr = ParakeetOnnxAsr("cpu").transcribe(audio, SR, "fr")
    assert tr.language == "fr" and all(w.end_us > w.start_us for w in tr.words)


def test_faster_whisper_tiny_words_have_probabilities(en):
    pytest.importorskip("faster_whisper")
    from videoflow.engines.asr.faster_whisper import FasterWhisperAsr

    audio, script = en
    tr = FasterWhisperAsr("cpu").transcribe(audio, SR, "en")
    assert tr.words and all(w.prob is not None and 0 <= w.prob <= 1 for w in tr.words)
    takes = [u for u in script["utterances"] if u["kind"] == "take"]
    for u in takes:
        inside = [w for w in tr.words if u["start_s"] - 0.6 <= w.start_us / 1e6 <= u["end_s"] + 0.6]
        assert len(inside) >= 6


@pytest.mark.parametrize("key", ["minilm"])
def test_text_embeddings_dim_384_and_ranking(key):
    pytest.importorskip("onnxruntime")
    from videoflow import engines  # noqa: F401
    from videoflow.engines import registry

    emb = registry.create("text_embed", key, prefer="cpu")
    texts = [
        "today we are going to assemble the video from the rushes",
        "today we will assemble the video from the rushes",
        "aujourd'hui nous allons assembler la video a partir des rushes",
        "the weather is cold and rainy in the mountains",
    ]
    v = emb.encode(texts)
    assert emb.dim == 384 and v.shape == (4, 384)
    assert np.allclose(np.linalg.norm(v, axis=1), 1.0, atol=1e-4)
    sims = v @ v.T
    assert sims[0, 1] > sims[0, 3] + 0.1  # paraphrase beats unrelated
    assert sims[0, 2] > sims[0, 3] + 0.1  # cross-lingual (EN/FR) too


def test_minilm_separates_french_retakes_from_related_sentences():
    pytest.importorskip("onnxruntime")
    from videoflow.engines.embed.onnx_st import OnnxTextEmbedder

    emb = OnnxTextEmbedder(prefer="cpu")
    v = np.asarray(
        emb.encode(
            [
                "Dans la boîte on trouve le câble USB-C et le chargeur 65 watts.",
                "Euh dans la boîte on a le câble USB-C et un chargeur de 65 watts.",
                "Le câble USB-C se branche en bas du téléphone.",
            ]
        )
    )
    assert v[0] @ v[1] > v[0] @ v[2] + 0.2


def test_dinov2_and_phash_separate_duplicates_from_different_shots(samples_dir, samples_manifest):
    pytest.importorskip("onnxruntime")
    pytest.importorskip("cv2")
    from videoflow.engines.vision import phash_hist as ph
    from videoflow.engines.vision.dinov2_onnx import Dinov2OnnxEmbedder

    dup, diff = samples_manifest["near_duplicate_groups"][0], samples_manifest["different_shots"][0]
    a, b = (sample_frames(samples_dir / n, fps=2.0) for n in dup)
    c = sample_frames(samples_dir / diff[1], fps=2.0)
    n = min(len(a), len(b), len(c))
    for emb in (ph.PhashHistEmbedder(), Dinov2OnnxEmbedder("cpu")):
        va, vb, vc = (emb.encode(f[:n]) for f in (a, b, c))
        dup_sim = (va * vb).sum(1)
        diff_sim = (va * vc).sum(1)
        assert dup_sim.min() > diff_sim.max() + 0.2, emb.model_id
    assert all(ph.is_near_duplicate(x, y) for x, y in zip(a[:n], b[:n], strict=True))
    assert not any(ph.is_near_duplicate(x, y) for x, y in zip(a[:n], c[:n], strict=True))
