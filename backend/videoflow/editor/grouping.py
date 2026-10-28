"""Retake grouping: which existing clip a newly imported clip is another take of.

Clips are compared sentence by sentence. Two sentences match when the blend of their
embedding cosine (MiniLM-L12) and word overlap reaches SENTENCE_MATCH; without vectors
(model not downloaded) word overlap alone must reach LEXICAL_MATCH. Thresholds come from
the benchmark in tests/fixtures/retake_pairs.json (spec 18). A clip is a retake of another
when at least MIN_COVERAGE of what either says (by words) is matched in the other.
"""

import hashlib
import io
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import numpy.typing as npt
from rapidfuzz.fuzz import token_set_ratio

from videoflow.analysis.types import Word
from videoflow.editor.topics import sentences

MODEL = "paraphrase-multilingual-minilm-l12-v2"
SENTENCE_MATCH = 0.68
LEXICAL_MATCH = 0.60
MIN_COVERAGE = 0.5

type Vectors = npt.NDArray[np.float32]


@dataclass(frozen=True)
class ClipText:
    """One clip's sentences and, when available, their L2-normalised embeddings."""

    key: str
    texts: list[str]
    vectors: Vectors | None = None


def clip_sentences(words: list[Word]) -> list[str]:
    """Sentences worth matching: two words or more."""
    return [s.text for s in sentences(words) if len(s.text.split()) >= 2]


def lexical(a: str, b: str) -> float:
    return float(token_set_ratio(a.casefold(), b.casefold())) / 100


def coverage(a: ClipText, b: ClipText) -> float:
    """Share of `a`'s words in sentences that have a match in `b`."""
    if not a.texts or not b.texts:
        return 0.0
    cosines = (
        a.vectors @ b.vectors.T if a.vectors is not None and b.vectors is not None else None
    )
    matched = total = 0
    for i, text in enumerate(a.texts):
        weight = len(text.split())
        total += weight
        for j, other in enumerate(b.texts):
            word = lexical(text, other)
            if cosines is not None:
                score, threshold = 0.5 * float(cosines[i, j]) + 0.5 * word, SENTENCE_MATCH
            else:
                score, threshold = word, LEXICAL_MATCH
            if score >= threshold:
                matched += weight
                break
    return matched / total


def retake_score(a: ClipText, b: ClipText) -> float:
    return max(coverage(a, b), coverage(b, a))


def best_match(new: ClipText, candidates: list[ClipText]) -> tuple[str, float] | None:
    """The candidate `new` is most clearly a retake of, if any reaches MIN_COVERAGE."""
    scored = [(retake_score(new, c), c.key) for c in candidates]
    score, key = max(scored, default=(0.0, ""))
    return (key, score) if score >= MIN_COVERAGE else None


def vectors_path(features_dir: Path, digest: str) -> Path:
    name = hashlib.sha256(f"{digest}:{MODEL}".encode()).hexdigest()
    return features_dir / "sentences" / f"{name}.npy"


def read_vectors(path: Path, count: int) -> Vectors | None:
    """Cached vectors, if present and matching the sentence count."""
    try:
        vectors = np.load(path, allow_pickle=False)
    except (OSError, ValueError):
        return None
    return vectors.astype(np.float32) if vectors.shape[:1] == (count,) else None


def encode_vectors(vectors: Vectors) -> bytes:
    buffer = io.BytesIO()
    np.save(buffer, np.asarray(vectors, dtype=np.float32), allow_pickle=False)
    return buffer.getvalue()
