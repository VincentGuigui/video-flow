"""S11 relations between segments (04 §4 with the 08 §3 corrections).

Text (speech segments):

1. Candidates: top-k nearest neighbours by embedding cosine (per-model, never an
   absolute cosine cut, 08 H15). Without embeddings: pairs sharing 2+ content tokens.
2. Local alignment of content-token ids (fillers and restart cues stripped).
3. ``text_sim = w * lex + (1 - w) * cos'`` where ``cos'`` is the cosine rescaled above
   the model's ``cosine_floor``.
4. Classification, shorter side ``s`` and longer side ``l``:

   * ``len(s) <= partial_max_ratio * len(l)`` and ``cov(s) >= partial_coverage``:
     matched at the start of ``l`` -> PARTIAL_RETAKE (``s`` is a false-start candidate);
     matched anywhere else -> **contained match**: no edge, a :class:`SplitSuggestion`
     for ``l`` instead (it holds more than one attempt).
   * else ``text_sim >= theta_text`` and ``min(cov) >= min_coverage`` -> RETAKE.

Visual: VISUAL_DUPLICATE only between two non-speech segments (08 D VISUAL_DUPLICATE).
For speech pairs, visual similarity is only recorded as ``details["same_setup"]``.

Sync: segments overlapping in synchronised time across an accepted
:class:`SyncResult` get SIMULTANEOUS.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from itertools import combinations

import numpy as np
import numpy.typing as npt

from videoflow.analysis.align_tokens import Alignment, align_local
from videoflow.analysis.textnorm import Token, Vocab, ends_with_cue, tokenize
from videoflow.analysis.types import (
    Relation,
    RelationScores,
    Segment,
    SyncResult,
    ThresholdProfile,
    Word,
)

type Matrix = npt.NDArray[np.floating]

PROFILES: dict[str, ThresholdProfile] = {
    p.model_id: p
    for p in (
        ThresholdProfile(
            model_id="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
            cosine_floor=0.2,
            theta_text=0.55,
            tau=0.5,
        ),
        ThresholdProfile(model_id="fake-bow-384", theta_text=0.55, tau=0.5),
    )
}
# Engines report the model-manifest key (engines/manifest.toml) as their model id.
PROFILES |= {
    key: PROFILES[repo].model_copy(update={"model_id": key})
    for key, repo in (
        (
            "paraphrase-multilingual-minilm-l12-v2",
            "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        ),
    )
}
"""Built-in per-model thresholds (provisional until Phase 0 calibration, 08 §2.2)."""

DEFAULT_PROFILE = ThresholdProfile(model_id="default")


def profile_for(model_id: str | None) -> ThresholdProfile:
    if model_id is None:
        return DEFAULT_PROFILE
    return PROFILES.get(model_id, DEFAULT_PROFILE.model_copy(update={"model_id": model_id}))


def embedding_input(text: str, profile: ThresholdProfile) -> str:
    """Text as given to the embedder, with the model's prefix (e5: ``"query: "``).

    Idempotent: the ONNX text engine also applies the manifest prefix, and an already
    prefixed text is left as is, so the prefix is never doubled.
    """
    prefix = profile.query_prefix
    return text if text.startswith(prefix) else f"{prefix}{text}"


def rescale_cosine(cosine: float, profile: ThresholdProfile) -> float:
    floor = profile.cosine_floor
    return float(min(1.0, max(0.0, (cosine - floor) / (1.0 - floor))))


# --------------------------------------------------------------------------- tokens


@dataclass(frozen=True, slots=True)
class SegmentTokens:
    """Matching view of a speech segment: content-token ids and their word indices."""

    segment_id: str
    asset_id: str
    start_us: int
    ids: tuple[int, ...]
    word_index: tuple[int, ...]
    """Absolute word index (in the asset transcript) of each content token."""
    end_cue: bool
    """The segment ends with a restart cue ("attends je reprends")."""
    filler_count: int = 0
    word_count: int = 0


def segment_tokens(
    segment: Segment, words: Sequence[Word], language: str, vocab: Vocab
) -> SegmentTokens:
    lo = segment.word_start or 0
    hi = segment.word_end if segment.word_end is not None else lo
    toks: list[Token] = tokenize([w.text for w in words[lo:hi]], language)
    content = [t for t in toks if t.content]
    return SegmentTokens(
        segment_id=segment.id,
        asset_id=segment.asset_id,
        start_us=segment.start_us,
        ids=tuple(vocab.ids(content)),
        word_index=tuple(t.word_index + lo for t in content),
        end_cue=ends_with_cue(toks),
        filler_count=sum(t.filler for t in toks),
        word_count=hi - lo,
    )


def prepare_tokens(
    segments: Sequence[Segment],
    words_by_asset: Mapping[str, Sequence[Word]],
    language: str = "fr",
    vocab: Vocab | None = None,
) -> dict[str, SegmentTokens]:
    """Token views for every speech segment, built in input order (deterministic ids)."""
    vocab = vocab or Vocab()
    return {
        s.id: segment_tokens(s, words_by_asset.get(s.asset_id, ()), language, vocab)
        for s in segments
        if s.kind == "speech"
    }


# --------------------------------------------------------------------------- text


@dataclass(frozen=True, slots=True)
class SplitSuggestion:
    """Split ``segment_id`` before each word index of ``cut_words`` (contained match)."""

    segment_id: str
    cut_words: tuple[int, ...]
    matched_with: str


@dataclass(frozen=True, slots=True)
class TextMatch:
    relation: Relation | None = None
    split: SplitSuggestion | None = None
    alignment: Alignment | None = None


def text_relation(
    a: SegmentTokens,
    b: SegmentTokens,
    cosine: float | None,
    profile: ThresholdProfile,
    max_gap: int = 3,
) -> TextMatch:
    if not a.ids or not b.ids:
        return TextMatch()
    al = align_local(a.ids, b.ids, max_gap=max_gap)
    if not al.matched:
        return TextMatch(alignment=al)
    cos = rescale_cosine(cosine, profile) if cosine is not None else None
    w = profile.lex_weight
    text_sim = al.lex if cos is None else w * al.lex + (1 - w) * cos
    scores = RelationScores(
        text_sim=round(text_sim, 6),
        lex=round(al.lex, 6),
        cosine=None if cosine is None else round(float(cosine), 6),
        cov_a=round(al.cov_a, 6),
        cov_b=round(al.cov_b, 6),
    )

    a_short = len(a.ids) <= len(b.ids)
    short, long_ = (a, b) if a_short else (b, a)
    cov_short = al.cov_a if a_short else al.cov_b
    lo, hi = al.span_b if a_short else al.span_a
    if len(short.ids) <= profile.partial_max_ratio * len(long_.ids) and (
        cov_short >= profile.partial_coverage
    ):
        if lo <= 1:
            false_start = short.end_cue or (
                short.asset_id == long_.asset_id and short.start_us < long_.start_us
            )
            rel = Relation(
                a=a.segment_id,
                b=b.segment_id,
                kind="partial_retake",
                score=round(cov_short, 6),
                scores=scores,
                details={"short": short.segment_id, "false_start": false_start},
            )
            return TextMatch(relation=rel, alignment=al)
        cuts = [long_.word_index[lo]]
        if hi < len(long_.ids):
            cuts.append(long_.word_index[hi])
        split = SplitSuggestion(long_.segment_id, tuple(cuts), short.segment_id)
        return TextMatch(split=split, alignment=al)

    if text_sim >= profile.theta_text and min(al.cov_a, al.cov_b) >= profile.min_coverage:
        rel = Relation(
            a=a.segment_id, b=b.segment_id, kind="retake", score=round(text_sim, 6), scores=scores
        )
        return TextMatch(relation=rel, alignment=al)
    return TextMatch(alignment=al)


def _normalised(rows: Matrix) -> Matrix:
    rows = np.asarray(rows, dtype=np.float64)
    norms = np.linalg.norm(rows, axis=-1, keepdims=True)
    return rows / np.where(norms > 0, norms, 1.0)


def top_k_pairs(vectors: Matrix, k: int) -> list[tuple[int, int, float]]:
    """Symmetric union of each row's ``k`` nearest neighbours: ``(i < j, cosine)``."""
    n = len(vectors)
    if n < 2:
        return []
    unit = _normalised(vectors)
    sims = unit @ unit.T
    np.fill_diagonal(sims, -np.inf)
    k = min(k, n - 1)
    nearest = np.argsort(-sims, axis=1, kind="stable")[:, :k]
    pairs: set[tuple[int, int]] = set()
    for i in range(n):
        for j in nearest[i]:
            pairs.add((min(i, int(j)), max(i, int(j))))
    return [(i, j, float(sims[i, j])) for i, j in sorted(pairs)]


def _lexical_pairs(views: Sequence[SegmentTokens], min_shared: int = 2) -> list[tuple[int, int]]:
    index: dict[int, set[int]] = {}
    for i, v in enumerate(views):
        for tok in set(v.ids):
            index.setdefault(tok, set()).add(i)
    shared: dict[tuple[int, int], int] = {}
    for members in index.values():
        for i, j in combinations(sorted(members), 2):
            shared[(i, j)] = shared.get((i, j), 0) + 1
    return sorted(p for p, n in shared.items() if n >= min_shared)


# --------------------------------------------------------------------------- visual


def visual_similarity(a: Matrix, b: Matrix) -> float:
    """Symmetrised mean best-match cosine between two frame-embedding sequences."""
    if len(a) == 0 or len(b) == 0:
        return 0.0
    sims = _normalised(a) @ _normalised(b).T
    return float(0.5 * (sims.max(axis=1).mean() + sims.max(axis=0).mean()))


# --------------------------------------------------------------------------- sync


def simultaneous_relations(
    segments: Sequence[Segment], syncs: Sequence[SyncResult], min_overlap: float = 0.25
) -> list[Relation]:
    """Segments overlapping in synchronised time (overlap >= 25 % of the shorter)."""
    by_asset: dict[str, list[Segment]] = {}
    for s in segments:
        by_asset.setdefault(s.asset_id, []).append(s)
    out: list[Relation] = []
    for sync in syncs:
        if not sync.accepted:
            continue
        for sa in by_asset.get(sync.asset_a, []):
            for sb in by_asset.get(sync.asset_b, []):
                b0, b1 = sb.start_us + sync.offset_us, sb.end_us + sync.offset_us
                overlap = min(sa.end_us, b1) - max(sa.start_us, b0)
                shorter = min(sa.end_us - sa.start_us, sb.end_us - sb.start_us)
                if shorter <= 0 or overlap < min_overlap * shorter:
                    continue
                out.append(
                    Relation(
                        a=sa.id,
                        b=sb.id,
                        kind="simultaneous",
                        score=1.0,
                        scores=RelationScores(
                            offset_us=-sync.offset_us, psr=sync.psr, drift_ppm=sync.drift_ppm
                        ),
                    )
                )
    return out


# --------------------------------------------------------------------------- all


@dataclass
class RelationsResult:
    relations: list[Relation] = field(default_factory=list)
    splits: list[SplitSuggestion] = field(default_factory=list)


def compute_relations(
    segments: Sequence[Segment],
    tokens: Mapping[str, SegmentTokens],
    profile: ThresholdProfile,
    text_embeddings: Mapping[str, npt.ArrayLike] | None = None,
    frame_embeddings: Mapping[str, Matrix] | None = None,
    syncs: Sequence[SyncResult] = (),
) -> RelationsResult:
    """All relations for a set of segments (pure; order follows ``segments``)."""
    result = RelationsResult()
    speech = [s for s in segments if s.kind == "speech" and s.id in tokens]
    views = [tokens[s.id] for s in speech]

    cosines: dict[tuple[int, int], float | None] = {}
    if text_embeddings is not None and all(s.id in text_embeddings for s in speech):
        matrix = np.stack([np.asarray(text_embeddings[s.id], dtype=np.float64) for s in speech])
        cosines.update({(i, j): c for i, j, c in top_k_pairs(matrix, profile.prefilter_top_k)})
    else:
        cosines.update({p: None for p in _lexical_pairs(views)})

    frames = frame_embeddings or {}
    split_seen: set[tuple[str, tuple[int, ...]]] = set()
    for (i, j), cos in sorted(cosines.items()):
        match = text_relation(views[i], views[j], cos, profile)
        if match.relation is not None:
            fa, fb = frames.get(speech[i].id), frames.get(speech[j].id)
            if fa is not None and fb is not None:
                match.relation.details["same_setup"] = round(visual_similarity(fa, fb), 6)
            result.relations.append(match.relation)
        if match.split is not None:
            key = (match.split.segment_id, match.split.cut_words)
            if key not in split_seen:
                split_seen.add(key)
                result.splits.append(match.split)

    visual = [s for s in segments if s.kind == "visual" and s.id in frames]
    if len(visual) > 1:
        means = np.stack([_normalised(frames[s.id]).mean(axis=0) for s in visual])
        for i, j, _ in top_k_pairs(means, profile.prefilter_top_k):
            sim = visual_similarity(frames[visual[i].id], frames[visual[j].id])
            if sim >= profile.theta_vis:
                result.relations.append(
                    Relation(
                        a=visual[i].id,
                        b=visual[j].id,
                        kind="visual_duplicate",
                        score=round(sim, 6),
                        scores=RelationScores(vis_sim=round(sim, 6)),
                    )
                )

    result.relations.extend(simultaneous_relations(segments, syncs))
    return result
