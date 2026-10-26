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


class EditorDocument(CamelModel):
    version: Literal[1] = 1
    clips: list[EditorClip] = Field(default_factory=list, max_length=10000)

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
            if (a.start, a.source_in, a.source_out) != (b.start, b.source_in, b.source_out):
                raise ValueError("Linked clips must have the same timing")
        return self


def layout(document: EditorDocument) -> tuple[list[EditorClip], int]:
    """Remove uncovered intervals globally, preserving explicit empty clips."""
    intervals: list[list[int]] = []
    for clip in sorted((c for c in document.clips if c.enabled), key=lambda c: c.start):
        end = clip.start + clip.duration
        if intervals and clip.start <= intervals[-1][1]:
            intervals[-1][1] = max(intervals[-1][1], end)
        else:
            intervals.append([clip.start, end])

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
