"""Sentence-transformer style text embedders (ONNX): multilingual e5-small, MiniLM.

Mean pooling over the attention mask, L2 normalisation. The e5 family needs a ``query: `` prefix
on every input; it comes from the manifest so a model swap cannot forget it. Absolute cosine
values are model specific (08 H15), hence one :class:`ThresholdProfile` per model id.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np

from videoflow.analysis.types import EngineInfo, ThresholdProfile
from videoflow.engines.manifest import ModelSpec, fetch, load_manifest
from videoflow.engines.protocols import Embeddings, TextRole
from videoflow.hw.ai import Prefer, make_session

DEFAULT_MODEL = "multilingual-e5-small"
BATCH = 32

# e5 cosines are compressed into roughly [0.7, 1.0], so its text threshold sits much higher
# than MiniLM's. Starting values; Phase 0 tunes them on real rushes (08 §2.2).
PROFILES: dict[str, dict[str, float]] = {
    "multilingual-e5-small": {"theta_text": 0.85, "theta_vis": 0.85},
    "paraphrase-multilingual-minilm-l12-v2": {"theta_text": 0.55, "theta_vis": 0.85},
}


def threshold_profile(model_key: str) -> ThresholdProfile:
    spec = load_manifest().get(model_key)
    return ThresholdProfile(
        model_id=model_key, query_prefix=spec.query_prefix, **PROFILES.get(model_key, {})
    )


def mean_pool(hidden: np.ndarray, mask: np.ndarray) -> np.ndarray:
    m = mask[..., None].astype(np.float32)
    summed = (hidden * m).sum(axis=1)
    return summed / np.clip(m.sum(axis=1), 1e-9, None)


class OnnxTextEmbedder:
    def __init__(self, model_key: str = DEFAULT_MODEL, prefer: Prefer = "auto") -> None:
        from tokenizers import Tokenizer

        spec: ModelSpec = load_manifest().get(model_key)
        if spec.purpose != "text-embed" or spec.dim is None:
            raise ValueError(f"{model_key} is not a text embedder")
        files = fetch(model_key)
        onnx_path = next(p for k, p in files.items() if k.endswith(".onnx"))
        tok_path = next(p for k, p in files.items() if k.endswith("tokenizer.json"))
        ms = make_session(onnx_path, prefer)
        self._session: Any = ms.session
        self._input_names = {i.name for i in self._session.get_inputs()}
        self._tok = Tokenizer.from_file(str(Path(tok_path)))
        self._tok.enable_truncation(max_length=spec.max_length)
        self._tok.enable_padding()
        self._spec = spec
        self.model_id = model_key
        self.dim = spec.dim
        self.info = EngineInfo(
            engine_id="onnx-text-embed", model_id=model_key, device=ms.device.value
        )

    @property
    def profile(self) -> ThresholdProfile:
        return threshold_profile(self.model_id)

    def prefix(self, role: TextRole) -> str:
        return self._spec.query_prefix if role == "query" else self._spec.passage_prefix

    def encode(self, texts: Sequence[str], role: TextRole = "passage") -> Embeddings:
        prefix = self.prefix(role)
        out = np.zeros((len(texts), self.dim), dtype=np.float32)
        for i in range(0, len(texts), BATCH):
            enc = self._tok.encode_batch([prefix + t for t in texts[i : i + BATCH]])
            ids = np.array([e.ids for e in enc], dtype=np.int64)
            mask = np.array([e.attention_mask for e in enc], dtype=np.int64)
            feeds: dict[str, np.ndarray] = {"input_ids": ids, "attention_mask": mask}
            if "token_type_ids" in self._input_names:
                feeds["token_type_ids"] = np.zeros_like(ids)
            hidden = self._session.run(None, feeds)[0]
            pooled = mean_pool(np.asarray(hidden, dtype=np.float32), mask)
            norms = np.linalg.norm(pooled, axis=1, keepdims=True)
            out[i : i + len(enc)] = pooled / np.clip(norms, 1e-12, None)
        return out
