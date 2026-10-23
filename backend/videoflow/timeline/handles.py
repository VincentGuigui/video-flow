"""Transition handle maths (integer frames, 08 §3 corrected alignment semantics).

A transition of ``T`` frames on the cut at frame ``c`` spans ``[c - before, c + after)``:

* ``before`` frames lie in the left clip's visible range and show the right clip ahead of
  its in point, so they consume the **right clip's head handle**;
* ``after`` frames lie in the right clip's visible range and show the left clip past its
  out point, so they consume the **left clip's tail handle**.

``center``: ``before = T // 2``, ``after = T - T // 2``. ``start`` (starts at the cut):
``after = T`` (left tail T). ``end`` (ends at the cut): ``before = T`` (right head T).
"""

from dataclasses import dataclass
from typing import Literal

from videoflow.core.time import Micros, Rational, frames

type AlignmentName = Literal["center", "start", "end"]

ALIGNMENTS: tuple[AlignmentName, ...] = ("center", "start", "end")


def split(duration: int, alignment: AlignmentName) -> tuple[int, int]:
    """``(before_cut, after_cut)`` frames of a transition of ``duration`` frames."""
    if duration < 0:
        raise ValueError("duration must be >= 0")
    if alignment == "start":
        return 0, duration
    if alignment == "end":
        return duration, 0
    before = duration // 2
    return before, duration - before


def max_duration(alignment: AlignmentName, before_budget: int, after_budget: int) -> int:
    """Longest transition whose ``split`` fits ``before_budget`` / ``after_budget``."""
    before_budget = max(0, before_budget)
    after_budget = max(0, after_budget)
    if alignment == "start":
        return after_budget
    if alignment == "end":
        return before_budget
    if after_budget > before_budget:
        return 2 * before_budget + 1
    return 2 * after_budget


def available_before(source_in_us: Micros, rate: Rational) -> int:
    """Source frames available before a clip's in point (at the project rate)."""
    return max(0, frames(source_in_us, rate))


def available_after(
    source_out_us: Micros, asset_duration_us: Micros | None, rate: Rational
) -> int | None:
    """Source frames available after a clip's out point, ``None`` when unknown."""
    if asset_duration_us is None:
        return None
    return max(0, frames(asset_duration_us, rate) - frames(source_out_us, rate))


@dataclass(frozen=True, slots=True)
class HandleCheck:
    """Outcome of the handle check (TR-06) for one transition."""

    duration: int
    alignment: AlignmentName
    missing_before: int
    """Right clip head frames missing from its source."""
    missing_after: int
    """Left clip tail frames missing from its source."""
    max_by_alignment: dict[AlignmentName, int]
    """Longest transition that fits the available media, per alignment (fix proposals)."""

    @property
    def ok(self) -> bool:
        return self.missing_before == 0 and self.missing_after == 0

    def describe(self) -> str:
        options = ", ".join(f"{a} <= {n} frames" for a, n in self.max_by_alignment.items())
        return (
            f"{self.duration}-frame {self.alignment} transition lacks "
            f"{self.missing_before} head frame(s) on the right clip and "
            f"{self.missing_after} tail frame(s) on the left clip; "
            f"fits: {options}; otherwise rendered with a freeze frame"
        )


def check(
    duration: int,
    alignment: AlignmentName,
    right_head_available: int | None,
    left_tail_available: int | None,
    *,
    before_visible: int | None = None,
    after_visible: int | None = None,
) -> HandleCheck:
    """Compare the handles a transition needs with the media around its clips.

    ``None`` availability (unknown asset duration) is treated as unlimited.
    ``before_visible`` / ``after_visible`` bound the fix proposals by the visible frames
    free on each side of the cut (they never cause a shortfall themselves).
    """
    before, after = split(duration, alignment)

    def budget(*limits: int | None) -> int:
        return min([duration, *(n for n in limits if n is not None)])

    head_budget = budget(right_head_available, before_visible)
    tail_budget = budget(left_tail_available, after_visible)
    return HandleCheck(
        duration=duration,
        alignment=alignment,
        missing_before=0 if right_head_available is None else max(0, before - right_head_available),
        missing_after=0 if left_tail_available is None else max(0, after - left_tail_available),
        max_by_alignment={
            a: min(duration, max_duration(a, head_budget, tail_budget)) for a in ALIGNMENTS
        },
    )
