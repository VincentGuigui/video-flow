"""Versioned editor extension; all editing time is integer project-rate frames."""

import math
from bisect import bisect_right
from typing import Literal

from pydantic import Field, model_validator

from videoflow.core.base import CamelModel


class Transform(CamelModel):
    x: float = 0
    y: float = 0
    width: float = Field(default=1920, gt=0)
    height: float = Field(default=1080, gt=0)
    crop_left: float = Field(default=0, ge=0, lt=1)
    crop_right: float = Field(default=0, ge=0, lt=1)
    crop_top: float = Field(default=0, ge=0, lt=1)
    crop_bottom: float = Field(default=0, ge=0, lt=1)

    @model_validator(mode="after")
    def valid(self) -> "Transform":
        if not all(
            math.isfinite(v)
            for v in (
                self.x,
                self.y,
                self.width,
                self.height,
                self.crop_left,
                self.crop_right,
                self.crop_top,
                self.crop_bottom,
            )
        ):
            raise ValueError("Transform values must be finite")
        if self.crop_left + self.crop_right >= 1 or self.crop_top + self.crop_bottom >= 1:
            raise ValueError("Crop must leave visible pixels")
        return self


class Background(CamelModel):
    mode: Literal["transparent", "color", "blur"] = "transparent"
    color: str = Field(default="#000000", pattern=r"^#[0-9a-fA-F]{6}$")


class ResizeReference(CamelModel):
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    transform: Transform


class HeldRange(CamelModel):
    """Assembly time retained by a standard audio trim, without a fake media clip."""

    start: int = Field(ge=0)
    end: int = Field(gt=0)

    @model_validator(mode="after")
    def valid(self) -> "HeldRange":
        if self.end <= self.start:
            raise ValueError("Retained time must have positive duration")
        return self


class EditorClip(CamelModel):
    id: str = Field(min_length=1)
    kind: Literal["video", "audio", "gap"]
    asset_id: str | None = None
    name: str
    start: int = Field(ge=0)
    source_in: int = Field(ge=0)
    source_out: int = Field(gt=0)
    layer: int = Field(default=0, ge=0, le=999)
    enabled: bool = True
    link_id: str | None = None
    gain_db: float = Field(default=0, ge=-60, le=24)
    transform: Transform = Field(default_factory=Transform)
    resize_reference: ResizeReference | None = None
    background: Background = Field(default_factory=Background)
    held_range: HeldRange | None = None

    @model_validator(mode="after")
    def valid(self) -> "EditorClip":
        if self.source_out <= self.source_in:
            raise ValueError("Clip must contain at least one frame")
        if self.kind != "gap" and self.asset_id is None:
            raise ValueError("Media clips require an asset")
        if self.kind == "gap" and (self.asset_id is not None or self.link_id is not None):
            raise ValueError("Empty clips have no asset or link")
        return self

    @property
    def duration(self) -> int:
        return self.source_out - self.source_in


type TransitionType = Literal["dissolve", "dip_black", "dip_white"]


class EditorTransition(CamelModel):
    """Transition at the cut between two adjacent video clips on one lane.

    It is dormant (ignored) while the clips are missing or not adjacent, so edits
    never fail because of a transition; see editor.transitions.
    """

    id: str = Field(min_length=1)
    left_id: str = Field(min_length=1)
    right_id: str = Field(min_length=1)
    type: TransitionType = "dissolve"
    duration: int = Field(default=15, ge=1, le=3600)
    """Requested frames, centred on the cut."""


class EditorDocument(CamelModel):
    version: Literal[1] = 1
    clips: list[EditorClip] = Field(default_factory=list, max_length=10000)
    transitions: list[EditorTransition] = Field(default_factory=list, max_length=10000)

    @model_validator(mode="after")
    def valid(self) -> "EditorDocument":
        if len({c.id for c in self.clips}) != len(self.clips):
            raise ValueError("Clip ids must be unique")
        links: dict[str, list[EditorClip]] = {}
        for clip in self.clips:
            if clip.link_id:
                links.setdefault(clip.link_id, []).append(clip)
        for pair in links.values():
            if len(pair) != 2 or {c.kind for c in pair} != {"video", "audio"}:
                raise ValueError("A link must join one video and one audio clip")
            a, b = pair
            if (a.start, a.duration) != (b.start, b.duration):
                raise ValueError("Linked clips must have the same timing")
        return self


def layout(document: EditorDocument) -> tuple[list[EditorClip], int]:
    """Remove uncovered intervals globally, preserving explicit empty clips."""
    intervals: list[list[int]] = []
    spans = [
        (
            min(c.start, c.held_range.start) if c.held_range else c.start,
            max(c.start + c.duration, c.held_range.end) if c.held_range else c.start + c.duration,
        )
        for c in document.clips
        if c.enabled
    ]
    for start, end in sorted(spans):
        if intervals and start <= intervals[-1][1]:
            intervals[-1][1] = max(intervals[-1][1], end)
        else:
            intervals.append([start, end])

    starts = [a for a, _ in intervals]
    prefix = [0]
    for a, b in intervals:
        prefix.append(prefix[-1] + b - a)

    def position(frame: int) -> int:
        index = bisect_right(starts, frame) - 1
        if index < 0:
            return 0
        start, end = intervals[index]
        return prefix[index] + min(frame, end) - start

    return [
        c.model_copy(update={"start": position(c.start)}) for c in document.clips if c.enabled
    ], sum(b - a for a, b in intervals)
