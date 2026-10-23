"""S14 quality metrics and take score (04 §7 with the 08 §3 corrections).

* Completeness is measured against the beat **consensus**, built from complete takes
  only (not false starts): a token belongs to it when present in more than half of
  them; at exactly half (e.g. 2 takes) it belongs when the most recent complete take
  has it.
* A metric that is missing (no ASR probability, no audio, no video...) is dropped and the
  remaining weights are renormalised, so the score stays in [0, 1].
* Video metrics are normalised within the beat. A false start multiplies the score by
  ``false_start_factor``.
"""

from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field

from videoflow.analysis.relations import SegmentTokens
from videoflow.analysis.types import Relation, TakeAnalysis, TakeFlagName

DEFAULT_WEIGHTS: dict[str, float] = {
    "completeness": 0.30,
    "fluency": 0.20,
    "audio": 0.15,
    "video": 0.15,
    "confidence": 0.10,
    "recency": 0.10,
}


@dataclass(frozen=True, slots=True)
class ScoreParams:
    weights: Mapping[str, float] = field(default_factory=lambda: dict(DEFAULT_WEIGHTS))
    false_start_factor: float = 0.3
    filler_rate_zero: float = 2.0
    """Fillers per 10 words at which fluency reaches 0."""
    filler_flag_rate: float = 1.0
    long_pause_penalty: float = 0.1
    loudness_range: tuple[float, float] = (-24.0, -12.0)
    loudness_falloff: float = 12.0
    clip_flag_ratio: float = 0.001


@dataclass(frozen=True, slots=True)
class TakeFeatures:
    """Raw per-take inputs; ``None`` means the metric is unavailable."""

    segment_id: str
    tokens: SegmentTokens | None = None
    false_start: bool = False
    recorded_at_us: int | None = None
    long_pauses: int = 0
    voiced_gaps: int = 0
    """VAD speech without words (fillers the ASR dropped)."""
    mean_prob: float | None = None
    loudness_lufs: float | None = None
    clip_ratio: float | None = None
    sharpness: float | None = None
    luma: float | None = None
    """Mean luma in [0, 1]."""
    clipped_luma_ratio: float | None = None
    shake: float | None = None


def false_start_ids(relations: Iterable[Relation], tokens: Mapping[str, SegmentTokens]) -> set[str]:
    """Short sides of PARTIAL_RETAKE marked as false start, plus segments ending in a cue."""
    out = {sid for sid, t in tokens.items() if t.end_cue}
    for rel in relations:
        if rel.kind == "partial_retake" and rel.details.get("false_start"):
            out.add(str(rel.details["short"]))
    return out


def consensus(takes: Sequence[TakeFeatures]) -> Counter[int]:
    """Consensus multiset of token ids over the complete takes (all takes if none)."""
    pool = [t for t in takes if t.tokens is not None and not t.false_start]
    if not pool:
        pool = [t for t in takes if t.tokens is not None]
    if not pool:
        return Counter()
    counts = [Counter(t.tokens.ids) for t in pool if t.tokens is not None]
    latest = max(
        range(len(pool)),
        key=lambda i: (pool[i].recorded_at_us is not None, pool[i].recorded_at_us or 0, i),
    )
    n = len(counts)
    out: Counter[int] = Counter()
    for tok in set().union(*counts):
        k = 1
        while True:
            support = sum(c[tok] >= k for c in counts)
            if 2 * support > n or (2 * support == n and counts[latest][tok] >= k):
                out[tok] = k
                k += 1
            else:
                break
    return out


def completeness(take: TakeFeatures, cons: Counter[int]) -> float | None:
    total = sum(cons.values())
    if take.tokens is None or total == 0:
        return None
    have = Counter(take.tokens.ids)
    return sum(min(have[t], m) for t, m in cons.items()) / total


def _minmax(values: Mapping[str, float], higher_is_better: bool) -> dict[str, float]:
    if not values:
        return {}
    lo, hi = min(values.values()), max(values.values())
    if hi - lo <= 1e-12:
        return dict.fromkeys(values, 1.0)
    return {
        k: (v - lo) / (hi - lo) if higher_is_better else (hi - v) / (hi - lo)
        for k, v in values.items()
    }


def _mean(values: Iterable[float | None]) -> float | None:
    vals = [v for v in values if v is not None]
    return sum(vals) / len(vals) if vals else None


def score_beat(
    takes: Sequence[TakeFeatures], params: ScoreParams | None = None
) -> list[TakeAnalysis]:
    """Score and flag every take of one beat; output follows input order."""
    params = params or ScoreParams()
    cons = consensus(takes)
    sharp = _minmax({t.segment_id: t.sharpness for t in takes if t.sharpness is not None}, True)
    shake = _minmax({t.segment_id: t.shake for t in takes if t.shake is not None}, False)
    expo_raw = {
        t.segment_id: abs(t.luma - 0.5) + (t.clipped_luma_ratio or 0.0)
        for t in takes
        if t.luma is not None
    }
    expo = _minmax(expo_raw, False)
    dated = [t for t in takes if t.recorded_at_us is not None]
    last_id = (
        max(dated, key=lambda t: t.recorded_at_us or 0).segment_id
        if len(dated) == len(takes) and dated
        else None
    )

    out: list[TakeAnalysis] = []
    for t in takes:
        flags: list[TakeFlagName] = []
        metrics: dict[str, float | None] = {"completeness": completeness(t, cons)}

        words = t.tokens.word_count if t.tokens is not None else 0
        if words > 0 and t.tokens is not None:
            rate = 10.0 * (t.tokens.filler_count + t.voiced_gaps) / words
            fluency = 1.0 - min(1.0, rate / params.filler_rate_zero)
            fluency -= params.long_pause_penalty * t.long_pauses
            metrics["fluency"] = max(0.0, fluency)
            if rate > params.filler_flag_rate:
                flags.append("fillers")
        else:
            metrics["fluency"] = None

        loud: float | None = None
        if t.loudness_lufs is not None:
            lo, hi = params.loudness_range
            dist = max(lo - t.loudness_lufs, t.loudness_lufs - hi, 0.0)
            loud = max(0.0, 1.0 - dist / params.loudness_falloff)
        clip: float | None = None
        if t.clip_ratio is not None:
            clip = 1.0 if t.clip_ratio <= params.clip_flag_ratio else 0.0
            if t.clip_ratio > params.clip_flag_ratio:
                flags.append("clipped_audio")
        metrics["audio"] = _mean([loud, clip])
        metrics["video"] = _mean(
            [sharp.get(t.segment_id), shake.get(t.segment_id), expo.get(t.segment_id)]
        )
        metrics["confidence"] = t.mean_prob
        if len(takes) == 1:
            metrics["recency"] = 1.0
        elif last_id is not None:
            metrics["recency"] = 1.0 if t.segment_id == last_id else 0.0
        else:
            metrics["recency"] = None
        if last_id is not None and t.segment_id == last_id and len(takes) > 1:
            flags.append("last_take")

        breakdown = {k: round(v, 6) for k, v in metrics.items() if v is not None}
        weights = {k: params.weights.get(k, 0.0) for k in breakdown}
        total_w = sum(weights.values())
        score = sum(breakdown[k] * w for k, w in weights.items()) / total_w if total_w else 0.0
        if t.false_start:
            flags.insert(0, "false_start")
            score *= params.false_start_factor
        out.append(
            TakeAnalysis(
                segment_id=t.segment_id,
                score=round(score, 6),
                breakdown=breakdown,
                flags=list(flags),
            )
        )
    return out
