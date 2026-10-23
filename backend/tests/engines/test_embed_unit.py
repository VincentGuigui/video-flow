from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from videoflow.engines.embed import onnx_st as st
from videoflow.hw.ai import Device


def test_mean_pool_ignores_padding():
    hidden = np.array([[[1.0, 1.0], [3.0, 3.0], [100.0, 100.0]]], dtype=np.float32)
    mask = np.array([[1, 1, 0]])
    assert st.mean_pool(hidden, mask).tolist() == [[2.0, 2.0]]


class FakeTok:
    def __init__(self):
        self.seen: list[str] = []

    def enable_truncation(self, **_):
        pass

    def enable_padding(self):
        pass

    def encode_batch(self, texts):
        self.seen += texts
        return [SimpleNamespace(ids=[1, 2, 0], attention_mask=[1, 1, 0]) for _ in texts]


class FakeSession:
    def __init__(self, names):
        self.names = names
        self.feeds = []

    def get_inputs(self):
        return [SimpleNamespace(name=n) for n in self.names]

    def run(self, _out, feeds):
        self.feeds.append(set(feeds))
        b = feeds["input_ids"].shape[0]
        hidden = np.tile(np.array([[[3.0, 4.0] + [0.0] * 382]], dtype=np.float32), (b, 3, 1))
        return [hidden]


@pytest.fixture
def embedder(monkeypatch, tmp_path):
    tok = FakeTok()
    sess = FakeSession(["input_ids", "attention_mask", "token_type_ids"])
    monkeypatch.setattr(
        st,
        "fetch",
        lambda key: {"onnx/m.onnx": tmp_path / "m.onnx", "onnx/tokenizer.json": tmp_path},
    )
    monkeypatch.setattr(
        st,
        "make_session",
        lambda p, prefer="auto", **k: SimpleNamespace(session=sess, device=Device.CPU),
    )
    import tokenizers

    monkeypatch.setattr(tokenizers.Tokenizer, "from_file", staticmethod(lambda p: tok))
    return st.OnnxTextEmbedder("multilingual-e5-small"), tok, sess


def test_e5_prefix_applied_and_output_normalised(embedder):
    emb, tok, sess = embedder
    out = emb.encode(["bonjour", "hello"])
    assert tok.seen == ["query: bonjour", "query: hello"]
    assert out.shape == (2, 384) and out.dtype == np.float32
    assert np.allclose(np.linalg.norm(out, axis=1), 1.0)
    assert out[0, 0] == pytest.approx(0.6) and out[0, 1] == pytest.approx(0.8)
    assert sess.feeds[0] == {"input_ids", "attention_mask", "token_type_ids"}
    emb.encode(["x"], role="query")
    assert tok.seen[-1] == "query: x"


def test_batches_over_32(embedder):
    emb, tok, _ = embedder
    out = emb.encode([f"t{i}" for i in range(70)])
    assert out.shape == (70, 384) and len(tok.seen) == 70
    assert np.allclose(np.linalg.norm(out, axis=1), 1.0)


def test_profiles_are_per_model():
    e5 = st.threshold_profile("multilingual-e5-small")
    mini = st.threshold_profile("paraphrase-multilingual-minilm-l12-v2")
    assert e5.model_id != mini.model_id
    assert e5.query_prefix == "query: " and mini.query_prefix == ""
    assert e5.theta_text > mini.theta_text  # e5 cosines are compressed upward


def test_rejects_non_text_model():
    with pytest.raises(ValueError):
        st.OnnxTextEmbedder("dinov2-small")
