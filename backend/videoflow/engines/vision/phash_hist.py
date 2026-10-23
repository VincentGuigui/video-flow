"""Perceptual hash + colour histogram: a cheap, model-free visual embedder and duplicate check."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
from scipy.fft import dctn

from videoflow.analysis.types import EngineInfo
from videoflow.engines.protocols import Embeddings, FrameArray

HASH_SIZE = 8
DCT_SIZE = 32
HIST_BINS = 16
NEAR_DUPLICATE_MAX_BITS = 10
"""Hamming distance (of 64 bits) up to which two frames count as the same picture."""


def _gray_small(frame: FrameArray, size: int) -> np.ndarray:
    f = np.asarray(frame, dtype=np.float64)
    gray = f @ np.array([0.299, 0.587, 0.114]) if f.ndim == 3 else f
    h, w = gray.shape
    # Area-average down to size x size (box filter on index bands), robust to any input size.
    ys = np.linspace(0, h, size + 1).astype(int)
    xs = np.linspace(0, w, size + 1).astype(int)
    out = np.empty((size, size))
    for r in range(size):
        for c in range(size):
            out[r, c] = gray[
                ys[r] : max(ys[r + 1], ys[r] + 1), xs[c] : max(xs[c + 1], xs[c] + 1)
            ].mean()
    return out


def phash_bits(frame: FrameArray) -> np.ndarray:
    """64 boolean hash bits: low-frequency 8x8 DCT block thresholded at its median."""
    dct = dctn(_gray_small(frame, DCT_SIZE), norm="ortho")[:HASH_SIZE, :HASH_SIZE]
    return (dct > np.median(dct.ravel()[1:])).ravel()  # skip the DC term in the median


def phash(frame: FrameArray) -> int:
    bits = phash_bits(frame)
    return int("".join("1" if b else "0" for b in bits), 2)


def hamming(a: int, b: int) -> int:
    return (a ^ b).bit_count()


def color_hist(frame: FrameArray) -> np.ndarray:
    """Concatenated per-channel histograms, L1-normalised per channel (48 values)."""
    f = np.asarray(frame)
    parts = []
    for ch in range(3):
        h, _ = np.histogram(f[..., ch], bins=HIST_BINS, range=(0, 256))
        parts.append(h / max(h.sum(), 1))
    return np.concatenate(parts)


def is_near_duplicate(
    a: FrameArray, b: FrameArray, max_bits: int = NEAR_DUPLICATE_MAX_BITS
) -> bool:
    return hamming(phash(a), phash(b)) <= max_bits


class PhashHistEmbedder:
    """Embedding = [hash bits as +-1, sqrt colour histogram], L2-normalised (dim 64 + 48)."""

    model_id = "phash-hist-v1"
    dim = HASH_SIZE * HASH_SIZE + 3 * HIST_BINS

    def __init__(self) -> None:
        self.info = EngineInfo(engine_id="phash-hist", model_id=self.model_id)

    def encode(self, frames: Sequence[FrameArray]) -> Embeddings:
        rows = np.zeros((len(frames), self.dim), dtype=np.float64)
        for i, frame in enumerate(frames):
            bits = np.where(phash_bits(frame), 1.0, -1.0) / np.sqrt(HASH_SIZE * HASH_SIZE)
            hist = np.sqrt(color_hist(frame))
            hist = hist / max(np.linalg.norm(hist), 1e-12)
            rows[i] = np.concatenate([bits, hist]) / np.sqrt(2.0)
        norms = np.linalg.norm(rows, axis=1, keepdims=True)
        return (rows / np.clip(norms, 1e-12, None)).astype(np.float32)
