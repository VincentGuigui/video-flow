from __future__ import annotations

import numpy as np
import pytest

from videoflow.engines.vision import phash_hist as ph


def scene(seed: int, size=(90, 160)) -> np.ndarray:
    """Smooth coloured blobs: a stand-in for a shot."""
    rng = np.random.default_rng(seed)
    base = rng.uniform(0, 255, size=(4, 6, 3))
    img = np.kron(base, np.ones((size[0] // 4 + 1, size[1] // 6 + 1, 1)))[: size[0], : size[1]]
    return img.astype(np.uint8)


def noisy(frame: np.ndarray, seed=0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    out = frame.astype(np.int16) + 6 + rng.integers(-3, 4, frame.shape)
    return np.clip(out, 0, 255).astype(np.uint8)


def test_phash_separates_near_duplicates_from_different_shots():
    a, b = scene(1), scene(2)
    near = ph.hamming(ph.phash(a), ph.phash(noisy(a)))
    far = ph.hamming(ph.phash(a), ph.phash(b))
    assert near <= ph.NEAR_DUPLICATE_MAX_BITS < far
    assert ph.is_near_duplicate(a, noisy(a)) and not ph.is_near_duplicate(a, b)


def test_phash_is_deterministic_and_size_independent():
    a = scene(3, (180, 320))
    assert ph.phash(a) == ph.phash(a.copy())
    small = a[::2, ::2]
    assert ph.hamming(ph.phash(a), ph.phash(small)) <= ph.NEAR_DUPLICATE_MAX_BITS


def test_embedder_unit_norm_and_similarity_order():
    emb = ph.PhashHistEmbedder()
    a, b = scene(1), scene(2)
    v = emb.encode([a, noisy(a), b])
    assert v.shape == (3, emb.dim) and v.dtype == np.float32
    assert np.allclose(np.linalg.norm(v, axis=1), 1.0, atol=1e-5)
    assert v[0] @ v[1] > 0.7 > v[0] @ v[2]
    assert emb.encode([]).shape == (0, emb.dim)


def test_dinov2_preprocess_shape_and_range():
    pytest.importorskip("cv2")
    from videoflow.engines.vision.dinov2_onnx import preprocess

    x = preprocess(scene(1, (180, 320)))
    assert x.shape == (3, 224, 224) and x.dtype == np.float32
    assert x.min() > -2.2 and x.max() < 2.7
    assert preprocess(scene(1, (300, 100))).shape == (3, 224, 224)  # portrait
