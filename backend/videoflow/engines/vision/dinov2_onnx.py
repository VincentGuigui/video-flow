"""DINOv2-small (quantised ONNX) visual embedder; CLS token, L2-normalised (dim 384)."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import cv2
import numpy as np

from videoflow.analysis.types import EngineInfo
from videoflow.engines.manifest import fetch
from videoflow.engines.protocols import Embeddings, FrameArray
from videoflow.hw.ai import Prefer, make_session

MODEL_KEY = "dinov2-small"
MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)
RESIZE, CROP = 256, 224
BATCH = 16


def preprocess(frame: FrameArray) -> np.ndarray:
    """Resize shortest edge to 256 (bicubic), centre-crop 224, normalise, CHW float32."""
    h, w = frame.shape[:2]
    scale = RESIZE / min(h, w)
    nh, nw = max(CROP, round(h * scale)), max(CROP, round(w * scale))
    img = cv2.resize(np.ascontiguousarray(frame), (nw, nh), interpolation=cv2.INTER_CUBIC)
    top, left = (nh - CROP) // 2, (nw - CROP) // 2
    img = img[top : top + CROP, left : left + CROP].astype(np.float32) / 255.0
    return ((img - MEAN) / STD).transpose(2, 0, 1)


def _warmup(session: Any) -> None:
    name = session.get_inputs()[0].name
    session.run(None, {name: np.zeros((1, 3, CROP, CROP), dtype=np.float32)})


class Dinov2OnnxEmbedder:
    dim = 384
    model_id = MODEL_KEY

    def __init__(self, prefer: Prefer = "auto") -> None:
        path = fetch(MODEL_KEY)["onnx/model_quantized.onnx"]
        ms = make_session(path, prefer, warmup=_warmup)
        self._session: Any = ms.session
        self._input = self._session.get_inputs()[0].name
        self.info = EngineInfo(engine_id="dinov2-onnx", model_id=MODEL_KEY, device=ms.device.value)

    def encode(self, frames: Sequence[FrameArray]) -> Embeddings:
        out = np.zeros((len(frames), self.dim), dtype=np.float32)
        for i in range(0, len(frames), BATCH):
            batch = np.stack([preprocess(f) for f in frames[i : i + BATCH]])
            hidden = self._session.run(None, {self._input: batch})[0]
            cls = np.asarray(hidden, dtype=np.float32)[:, 0, :]
            out[i : i + len(cls)] = cls / np.clip(
                np.linalg.norm(cls, axis=1, keepdims=True), 1e-12, None
            )
        return out
