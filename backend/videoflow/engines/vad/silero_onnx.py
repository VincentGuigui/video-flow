"""Silero VAD v5 (ONNX) run through the hw.ai session factory."""

from __future__ import annotations

from typing import Any

import numpy as np
import numpy.typing as npt
from scipy.signal import resample_poly

from videoflow.analysis.types import EngineInfo
from videoflow.core.time import US_PER_SECOND, TimeRange
from videoflow.engines.manifest import fetch
from videoflow.engines.protocols import AudioArray
from videoflow.hw.ai import Prefer, make_session

MODEL_KEY = "silero-vad"
TARGET_SR = 16_000
WINDOW = 512  # samples per step at 16 kHz (the model is fixed to 512 / 256 at 8 kHz)
CONTEXT = 64


def probs_to_ranges(
    probs: npt.NDArray[np.float32],
    *,
    window_s: float,
    total_s: float,
    threshold: float = 0.5,
    neg_threshold: float | None = None,
    min_speech_s: float = 0.25,
    min_silence_s: float = 0.1,
    pad_s: float = 0.03,
) -> list[tuple[float, float]]:
    """Hysteresis over per-window speech probabilities, then merge, filter and pad (seconds)."""
    off = threshold - 0.15 if neg_threshold is None else neg_threshold
    raw: list[list[float]] = []
    start: float | None = None
    for i, p in enumerate(probs.tolist()):
        t = i * window_s
        if start is None and p >= threshold:
            start = t
        elif start is not None and p < off:
            raw.append([start, t])
            start = None
    if start is not None:
        raw.append([start, total_s])
    merged: list[list[float]] = []
    for s, e in raw:
        if merged and s - merged[-1][1] < min_silence_s:
            merged[-1][1] = e
        else:
            merged.append([s, e])
    return [
        (max(0.0, s - pad_s), min(total_s, e + pad_s)) for s, e in merged if e - s >= min_speech_s
    ]


def _warmup(session: Any) -> None:
    zeros = np.zeros((1, CONTEXT + WINDOW), dtype=np.float32)
    state = np.zeros((2, 1, 128), dtype=np.float32)
    session.run(None, {"input": zeros, "state": state, "sr": np.array(TARGET_SR, dtype=np.int64)})


class SileroVad:
    def __init__(self, prefer: Prefer = "auto", *, threshold: float = 0.5) -> None:
        path = fetch(MODEL_KEY)["onnx/model.onnx"]
        # Tiny recurrent model: the NPU/GPU round trip per 32 ms window rarely pays, but the
        # chain still decides (it falls back to CPU on any failure).
        ms = make_session(path, prefer, warmup=_warmup)
        self._session = ms.session
        self.threshold = threshold
        self.info = EngineInfo(engine_id="silero-vad", model_id=MODEL_KEY, device=ms.device.value)

    def probabilities(self, audio: AudioArray) -> npt.NDArray[np.float32]:
        """Speech probability for each consecutive 512-sample window of 16 kHz audio."""
        n = len(audio) // WINDOW + (1 if len(audio) % WINDOW else 0)
        padded = np.zeros(n * WINDOW, dtype=np.float32)
        padded[: len(audio)] = audio
        state = np.zeros((2, 1, 128), dtype=np.float32)
        sr = np.array(TARGET_SR, dtype=np.int64)
        context = np.zeros(CONTEXT, dtype=np.float32)
        out = np.zeros(n, dtype=np.float32)
        for i in range(n):
            chunk = padded[i * WINDOW : (i + 1) * WINDOW]
            x = np.concatenate([context, chunk])[None, :]
            prob, state = self._session.run(None, {"input": x, "state": state, "sr": sr})
            out[i] = float(prob.reshape(-1)[0])
            context = chunk[-CONTEXT:]
        return out

    def speech_ranges(self, audio: AudioArray, sample_rate: int) -> list[TimeRange]:
        x = np.asarray(audio, dtype=np.float32)
        if sample_rate != TARGET_SR:
            x = resample_poly(x, TARGET_SR, sample_rate).astype(np.float32)
        if x.size == 0:
            return []
        probs = self.probabilities(x)
        spans = probs_to_ranges(
            probs,
            window_s=WINDOW / TARGET_SR,
            total_s=len(x) / TARGET_SR,
            threshold=self.threshold,
        )
        return [
            TimeRange(start_us=round(s * US_PER_SECOND), end_us=round(e * US_PER_SECOND))
            for s, e in spans
        ]
