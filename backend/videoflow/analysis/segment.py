"""S9 segmentation (04 S9 with the 08 §3 corrections).

Speech: words -> utterances (gap rules, plus a split right after a restart cue followed
by more speech) -> blocks of utterances = segments. A block ends on a long gap, on a shot
cut inside a medium gap, after an utterance that ends with a restart cue, or when the
next utterance restarts: its first words cover the first words of *any* utterance of the
block (08 §3: not only the block start). Visual: shots minus speech, kept when long
enough, long ones split evenly.

All functions are pure; segment ids come from ``new_id`` (inject a counter in tests).
"""

import math
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from videoflow.analysis.align_tokens import align_global
from videoflow.analysis.textnorm import Token, Vocab, content_tokens, ends_with_cue, tokenize
from videoflow.analysis.types import Segment, SegmentRemap, Shot, Utterance, Word
from videoflow.core import ids
from videoflow.core.time import Micros, TimeRange

type IdFactory = Callable[[], str]

_SENTENCE_END_RE = re.compile(r"[.!?…]['\")\]]*$")


def _new_segment_id() -> str:
    return ids.new_id(ids.SEGMENT)


@dataclass(frozen=True, slots=True)
class SegmentationParams:
    """Tunable gaps (Phase 0 calibrates them on real rushes, 08 §2.2)."""

    utterance_gap_us: Micros = 800_000
    sentence_gap_us: Micros = 400_000
    block_gap_us: Micros = 2_000_000
    shot_gap_us: Micros = 500_000
    restart_words: int = 5
    """N: how many leading content tokens are compared for a restart."""
    restart_coverage: float = 0.7
    restart_min_tokens: int = 2
    visual_min_us: Micros = 1_500_000
    visual_max_us: Micros = 20_000_000


DEFAULT_PARAMS = SegmentationParams()


def _join(words: Sequence[Word]) -> str:
    return " ".join(w.text.strip() for w in words if w.text.strip())


def _cue_split_points(words: Sequence[Word], lo: int, hi: int, language: str) -> list[int]:
    """Word indices in (lo, hi) right after a restart cue that has speech on both sides."""
    tokens = tokenize([w.text for w in words[lo:hi]], language)
    points: list[int] = []
    for k, tok in enumerate(tokens):
        if not tok.cue or (k + 1 < len(tokens) and tokens[k + 1].cue):
            continue  # not the last token of a cue run
        if any(t.content for t in tokens[:k]) and any(t.content for t in tokens[k + 1 :]):
            nxt = tokens[k + 1].word_index + lo
            if nxt not in points and lo < nxt < hi:
                points.append(nxt)
    return points


def split_utterances(
    words: Sequence[Word],
    asset_id: str,
    language: str = "fr",
    params: SegmentationParams = DEFAULT_PARAMS,
) -> list[Utterance]:
    """Utterances: split on gaps > 0.8 s, or sentence end + gap > 0.4 s, or after a cue."""
    bounds: list[int] = [0]
    for i in range(1, len(words)):
        gap = words[i].start_us - words[i - 1].end_us
        sentence_end = bool(_SENTENCE_END_RE.search(words[i - 1].text.strip()))
        if gap > params.utterance_gap_us or (sentence_end and gap > params.sentence_gap_us):
            bounds.append(i)
    bounds.append(len(words))

    out: list[Utterance] = []
    for lo, hi in zip(bounds, bounds[1:], strict=False):
        if hi <= lo:
            continue
        cuts = [lo, *_cue_split_points(words, lo, hi, language), hi]
        for a, b in zip(cuts, cuts[1:], strict=False):
            out.append(
                Utterance(
                    asset_id=asset_id,
                    start_us=words[a].start_us,
                    end_us=words[b - 1].end_us,
                    word_start=a,
                    word_end=b,
                    text=_join(words[a:b]),
                )
            )
    return out


def _shot_cut_between(shots: Sequence[Shot], t0: Micros, t1: Micros) -> bool:
    return any(t0 < s.start_us <= t1 for s in shots)


def _overlapping_shots(shots: Sequence[Shot], start: Micros, end: Micros) -> list[str]:
    return [s.id for s in shots if s.start_us < end and s.end_us > start]


def _is_restart(
    head: Sequence[int], block_heads: Sequence[Sequence[int]], params: SegmentationParams
) -> bool:
    if len(head) < params.restart_min_tokens:
        return False
    for other in block_heads:
        n = min(len(head), len(other))
        if n < params.restart_min_tokens:
            continue
        matched = align_global(head[:n], other[:n]).matched
        if matched / n >= params.restart_coverage:
            return True
    return False


def segment_speech(
    words: Sequence[Word],
    utterances: Sequence[Utterance],
    asset_id: str,
    language: str = "fr",
    shots: Sequence[Shot] = (),
    params: SegmentationParams = DEFAULT_PARAMS,
    new_id: IdFactory = _new_segment_id,
) -> list[Segment]:
    """Merge utterances into blocks (one attempt each) and return speech segments."""
    vocab = Vocab()
    toks: list[list[Token]] = [
        tokenize([w.text for w in words[u.word_start : u.word_end]], language) for u in utterances
    ]
    heads = [vocab.ids(content_tokens(t))[: params.restart_words] for t in toks]

    blocks: list[list[int]] = []
    for k, u in enumerate(utterances):
        if blocks:
            prev = utterances[blocks[-1][-1]]
            gap = u.start_us - prev.end_us
            first_real = next((t for t in toks[k] if not t.filler), None)
            new_block = (
                gap > params.block_gap_us
                or (gap > params.shot_gap_us and _shot_cut_between(shots, prev.end_us, u.start_us))
                or ends_with_cue(toks[blocks[-1][-1]])
                or (first_real is not None and first_real.cue)
                or _is_restart(heads[k], [heads[j] for j in blocks[-1]], params)
            )
            if not new_block:
                blocks[-1].append(k)
                continue
        blocks.append([k])

    segments: list[Segment] = []
    for block in blocks:
        first, last = utterances[block[0]], utterances[block[-1]]
        segments.append(
            Segment(
                id=new_id(),
                asset_id=asset_id,
                kind="speech",
                start_us=first.start_us,
                end_us=last.end_us,
                text=_join(words[first.word_start : last.word_end]),
                word_start=first.word_start,
                word_end=last.word_end,
                utterance_count=len(block),
                shot_ids=_overlapping_shots(shots, first.start_us, last.end_us),
            )
        )
    return segments


def _subtract(range_: TimeRange, holes: Sequence[TimeRange]) -> list[TimeRange]:
    pieces = [range_]
    for hole in sorted(holes, key=lambda r: r.start_us):
        nxt: list[TimeRange] = []
        for p in pieces:
            if hole.end_us <= p.start_us or hole.start_us >= p.end_us:
                nxt.append(p)
                continue
            if hole.start_us > p.start_us:
                nxt.append(TimeRange(start_us=p.start_us, end_us=hole.start_us))
            if hole.end_us < p.end_us:
                nxt.append(TimeRange(start_us=hole.end_us, end_us=p.end_us))
        pieces = nxt
    return pieces


def segment_visual(
    shots: Sequence[Shot],
    speech: Sequence[TimeRange],
    asset_id: str,
    params: SegmentationParams = DEFAULT_PARAMS,
    new_id: IdFactory = _new_segment_id,
) -> list[Segment]:
    """Non-speech parts of shots, >= 1.5 s, split evenly into pieces <= 20 s."""
    out: list[Segment] = []
    for shot in sorted(shots, key=lambda s: (s.start_us, s.index)):
        whole = TimeRange(start_us=shot.start_us, end_us=shot.end_us)
        for piece in _subtract(whole, speech):
            if piece.duration_us < params.visual_min_us:
                continue
            n = max(1, math.ceil(piece.duration_us / params.visual_max_us))
            edges = [piece.start_us + piece.duration_us * i // n for i in range(n + 1)]
            for a, b in zip(edges, edges[1:], strict=False):
                out.append(
                    Segment(
                        id=new_id(),
                        asset_id=asset_id,
                        kind="visual",
                        start_us=a,
                        end_us=b,
                        shot_ids=[shot.id],
                    )
                )
    return out


def split_segment(
    segment: Segment,
    words: Sequence[Word],
    cut_words: Sequence[int],
    new_id: IdFactory = _new_segment_id,
) -> list[Segment]:
    """Split a speech segment before each word index in ``cut_words`` (contained match)."""
    if segment.word_start is None or segment.word_end is None:
        return [segment]
    lo, hi = segment.word_start, segment.word_end
    cuts = sorted({c for c in cut_words if lo < c < hi})
    if not cuts:
        return [segment]
    edges = [lo, *cuts, hi]
    out: list[Segment] = []
    for a, b in zip(edges, edges[1:], strict=False):
        start, end = words[a].start_us, words[b - 1].end_us
        out.append(
            segment.model_copy(
                update={
                    "id": new_id(),
                    "start_us": start,
                    "end_us": end,
                    "text": _join(words[a:b]),
                    "word_start": a,
                    "word_end": b,
                    "utterance_count": 1,
                    "shot_ids": list(segment.shot_ids),
                }
            )
        )
    return out


def remap_segments(
    old: Sequence[Segment], new: Sequence[Segment], threshold: float = 0.5
) -> SegmentRemap:
    """Map old segment ids to the new segment of the same asset and kind with best IoU."""
    by_asset: dict[tuple[str, str], list[Segment]] = {}
    for s in new:
        by_asset.setdefault((s.asset_id, str(s.kind)), []).append(s)
    remap = SegmentRemap(threshold=threshold)
    for o in old:
        best_id, best_iou = None, 0.0
        for cand in by_asset.get((o.asset_id, str(o.kind)), []):
            iou = o.range.iou(cand.range)
            if iou > best_iou:
                best_id, best_iou = cand.id, iou
        if best_id is not None and best_iou >= threshold:
            remap.mapping[o.id] = best_id
            remap.iou[o.id] = best_iou
        else:
            remap.unmatched.append(o.id)
    return remap
