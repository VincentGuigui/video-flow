"""S16 ordering and default selection (04 §9).

* Beats are ordered by the recording time of their earliest complete take (asset
  creation time + segment start, sync-corrected by the caller). When any beat lacks a
  recording time, every beat falls back to natural file-name order, then segment start.
* Beats with role ``intro`` / ``outro`` are moved first / last and reported in
  ``moved`` so the UI can flag the suggestion.
* Default take: highest score; ties broken by the LLM best take, then by recency.
"""

import re
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, field

from videoflow.analysis.types import ProposedBeat, TakeAnalysis


@dataclass(frozen=True, slots=True)
class SegmentClock:
    segment_id: str
    asset_name: str
    start_us: int
    recorded_at_us: int | None = None
    """Absolute recording time of the segment start (None when unknown)."""


@dataclass
class OrderResult:
    beats: list[ProposedBeat] = field(default_factory=list)
    moved: list[str] = field(default_factory=list)
    """Keys of beats moved by the intro/outro rule."""
    by_recording_time: bool = True


def natural_key(text: str) -> tuple[tuple[int, int | str], ...]:
    """``clip2`` < ``clip10``; case-insensitive."""
    return tuple(
        (0, int(part)) if part.isdigit() else (1, part.casefold())
        for part in re.split(r"(\d+)", text)
        if part
    )


def _anchor(beat: ProposedBeat, false_starts: Collection[str]) -> list[str]:
    complete = [s for s in beat.segment_ids if s not in false_starts]
    return complete or list(beat.segment_ids)


def order_beats(
    beats: Sequence[ProposedBeat],
    clocks: Mapping[str, SegmentClock],
    false_starts: Collection[str] = (),
) -> OrderResult:
    anchors = {b.key: [clocks[s] for s in _anchor(b, false_starts) if s in clocks] for b in beats}
    timed = all(a and all(c.recorded_at_us is not None for c in a) for a in anchors.values())

    def key(item: tuple[int, ProposedBeat]) -> tuple[object, ...]:
        pos, beat = item
        cs = anchors[beat.key]
        if not cs:
            return (2, pos)
        if timed:
            return (0, min(c.recorded_at_us or 0 for c in cs), pos)
        first = min(cs, key=lambda c: (natural_key(c.asset_name), c.start_us))
        return (1, natural_key(first.asset_name), first.start_us, pos)

    ordered = [b for _, b in sorted(enumerate(beats), key=key)]
    result = OrderResult(by_recording_time=timed)
    intros = [b for b in ordered if b.role == "intro"]
    outros = [b for b in ordered if b.role == "outro"]
    middle = [b for b in ordered if b.role not in ("intro", "outro")]
    final = intros + middle + outros
    for i, b in enumerate(final):
        if b.role in ("intro", "outro") and ordered.index(b) != i:
            result.moved.append(b.key)
    result.beats = final
    return result


def select_default(
    takes: Sequence[TakeAnalysis],
    llm_best: str | None = None,
    recorded_at: Mapping[str, int | None] | None = None,
) -> str | None:
    """Highest score; ties broken by the LLM's best take, then by the latest recording."""
    if not takes:
        return None
    rec = recorded_at or {}

    def key(item: tuple[int, TakeAnalysis]) -> tuple[float, bool, int, int]:
        pos, t = item
        return (round(t.score or 0.0, 9), t.segment_id == llm_best, rec.get(t.segment_id) or 0, pos)

    return max(enumerate(takes), key=key)[1].segment_id
