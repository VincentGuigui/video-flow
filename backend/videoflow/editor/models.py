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
    rotation: float = Field(default=0, ge=-3600, le=3600)
    """Degrees, clockwise, around the centre of the box (docs/features/keyframes.md)."""
    opacity: float = Field(default=1, ge=0, le=1)

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
                self.rotation,
                self.opacity,
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


class Keyframe(CamelModel):
    """The clip's transform at one source frame (docs/features/keyframes.md).

    Between two keyframes every value is interpolated; `ease` shapes the change that starts
    at this keyframe (`smooth` eases in and out). Before the first and after the last
    keyframe the transform holds.
    """

    frame: int = Field(ge=0)
    transform: Transform
    ease: Literal["linear", "smooth"] = "smooth"


class VolumeRange(CamelModel):
    """Lowered or muted audio over a source range (docs/features/clip-effects.md); ramps sit
    outside the range."""

    start: int = Field(ge=0)
    end: int = Field(gt=0)
    gain_db: float = Field(default=-60, ge=-60, le=0)
    """-60 dB means silence."""
    ramp: int = Field(default=4, ge=0)
    kind: Literal["mute", "duck"] = "mute"

    @model_validator(mode="after")
    def valid(self) -> "VolumeRange":
        if self.end <= self.start:
            raise ValueError("A volume range must last at least one frame")
        return self

    @property
    def factor(self) -> float:
        return 0.0 if self.gain_db <= -60 else float(10 ** (self.gain_db / 20))


class Title(CamelModel):
    """Text of a text clip (docs/features/clip-effects.md), laid out by editor.titles."""

    text: str = Field(min_length=1, max_length=1000)
    """Lines separated by newlines."""
    style: Literal["title", "lower_third"] = "title"
    size: float = Field(default=0.08, ge=0.02, le=0.3)
    """Font size of the first line, relative to the picture height."""
    color: str = Field(default="#ffffff", pattern=r"^#[0-9a-fA-F]{6}$")
    box: bool = False
    box_color: str = Field(default="#000000", pattern=r"^#[0-9a-fA-F]{6}$")
    box_opacity: float = Field(default=0.75, ge=0, le=1)

    @model_validator(mode="after")
    def valid(self) -> "Title":
        if not self.text.strip():
            raise ValueError("A title needs text")
        return self


class EditorClip(CamelModel):
    id: str = Field(min_length=1)
    kind: Literal["video", "audio", "gap", "text"]
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
    fade_in: int = Field(default=0, ge=0)
    """Frames fading in at the clip's start (picture from what lies below, audio from silence)."""
    fade_out: int = Field(default=0, ge=0)
    speed: float = Field(default=1.0, ge=0.1, le=10)
    """Playback speed: source frames per timeline frame (docs/features/clip-effects.md)."""
    keyframes: list[Keyframe] = Field(default_factory=list, max_length=1000)
    """Animated transform of a video clip, in source frames (docs/features/keyframes.md)."""
    volume_ranges: list[VolumeRange] = Field(default_factory=list, max_length=2000)
    title: Title | None = None
    """Text drawn by a text clip; text clips have no asset and play on video lanes."""
    still_frame: int | None = Field(default=None, ge=0)
    """Source frame a still clip shows for its whole length (0 for a still image); None for
    moving clips. A still clip has no source limit: its range only measures its length
    (docs/features/still-images.md)."""

    @model_validator(mode="after")
    def valid(self) -> "EditorClip":
        if self.source_out <= self.source_in:
            raise ValueError("Clip must contain at least one frame")
        if self.kind in ("video", "audio") and self.asset_id is None:
            raise ValueError("Media clips require an asset")
        if self.kind in ("gap", "text") and (self.asset_id is not None or self.link_id is not None):
            raise ValueError("Empty and text clips have no asset or link")
        if (self.kind == "text") != (self.title is not None):
            raise ValueError("Text clips, and only they, have a title")
        if self.kind == "text" and self.speed != 1:
            raise ValueError("Text clips play at normal speed")
        if self.still_frame is not None and (self.kind != "video" or self.speed != 1):
            raise ValueError("Only video clips can be still, at normal speed")
        if self.keyframes:
            if self.kind != "video":
                raise ValueError("Only video clips have keyframes")
            frames = [k.frame for k in self.keyframes]
            if len(set(frames)) != len(frames):
                raise ValueError("Keyframes must be at distinct frames")
            self.keyframes.sort(key=lambda k: k.frame)
        return self

    @property
    def still(self) -> bool:
        return self.still_frame is not None

    @property
    def span(self) -> int:
        """Source frames used by the clip."""
        return self.source_out - self.source_in

    @property
    def duration(self) -> int:
        """Timeline frames: the source span played at `speed`."""
        # Half up, like the editor's Math.round.
        return self.span if self.speed == 1 else max(1, int(self.span / self.speed + 0.5))

    def timeline_frames(self, source_frames: int) -> int:
        """Timeline length of `source_frames` of this clip's source (rounded down)."""
        return int(source_frames // self.speed) if self.speed != 1 else source_frames

    def source_frames(self, timeline_frames: int) -> int:
        return timeline_frames if self.speed == 1 else int(timeline_frames * self.speed + 0.5)


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
            if (a.start, a.duration, a.speed) != (b.start, b.duration, b.speed):
                raise ValueError("Linked clips must have the same timing and speed")
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
