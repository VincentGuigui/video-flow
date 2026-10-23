"""Resolved timeline contract: the flat, frame-quantised edit (data types only).

Produced from ``project.json`` by the resolver (WP6) and consumed by both the OTIO
compiler (WP7) and the FFmpeg render (WP8), so they describe the same edit.

Conventions:

* All timeline positions and durations are **integer frames** at ``rate``. A main-line
  clip covers ``frames(source_out) - frames(source_in)`` frames; ``timeline_start`` is
  the cumulative sum of the previous clips' frame counts (core/time.py rule).
* Source ranges stay in microseconds (exact), with the quantised frame bounds alongside.
* Handles are the extra source frames a transition consumes beyond the visible range:
  ``center`` takes T/2 from each side (left clip tail, right clip head; odd T gives the
  extra frame to the right clip's head), ``start`` takes T from the right clip's head,
  ``end`` takes T from the left clip's tail. Total frames = sum of visible clip frames.
* A dormant transition (items not adjacent any more) is listed separately and renders
  as a hard cut; the resolver adds a warning for it.
"""

from typing import Annotated, Literal

from pydantic import Field

from videoflow.core.base import CamelModel, UnknownValue
from videoflow.core.time import Micros, Rational

type TrackIdName = Literal["V1", "A1", "V2", "A2"]
TrackId = Annotated[TrackIdName | UnknownValue, Field(union_mode="left_to_right")]


class ResolvedAudio(CamelModel):
    mode: Literal["linked", "replaced", "muted", "mix"] | UnknownValue = "linked"
    asset_id: str | None = None
    """Asset the audio comes from (the clip's own asset unless replaced)."""
    source_in_us: Micros | None = None
    gain_db: float = 0.0
    fade_in_frames: int = Field(default=0, ge=0)
    fade_out_frames: int = Field(default=0, ge=0)


class ResolvedClip(CamelModel):
    """One clip on a track at an absolute frame position."""

    item_id: str
    track: TrackId
    asset_id: str
    beat_id: str | None = None
    segment_id: str | None = None
    take_status: str | None = None
    timeline_start: int = Field(ge=0)
    """First visible frame on the timeline."""
    duration: int = Field(ge=0)
    """Visible frame count."""
    source_in_us: Micros
    source_out_us: Micros
    source_in_frame: int
    """``frames(source_in_us)``: first visible source frame."""
    handle_before: int = Field(default=0, ge=0)
    """Source frames consumed before ``source_in_frame`` by an incoming transition."""
    handle_after: int = Field(default=0, ge=0)
    """Source frames consumed after the visible range by an outgoing transition."""
    available_before: int | None = None
    """Source frames available before the visible range (None if unknown)."""
    available_after: int | None = None
    enabled: bool = True
    audio: ResolvedAudio | None = None
    fit: Literal["fill", "fit"] | UnknownValue | None = None
    clamped: bool = False
    """Overlay position or length was clamped to the main line."""

    @property
    def timeline_end(self) -> int:
        return self.timeline_start + self.duration


class ResolvedTransition(CamelModel):
    transition_id: str
    after_item_id: str
    before_item_id: str
    type: str
    state: Literal["active", "dormant"]
    alignment: Literal["center", "start", "end"] | UnknownValue = "center"
    duration: int = Field(default=0, ge=0)
    """Frames (0 for a dormant transition)."""
    cut_frame: int | None = None
    """Timeline frame of the cut (start of the right clip); None when dormant."""
    left_frames: int = Field(default=0, ge=0)
    """Frames of the transition before the cut (left clip's tail handle)."""
    right_frames: int = Field(default=0, ge=0)
    """Frames after the cut (right clip's head handle)."""
    audio: Literal["follow", "cut", "crossfade"] | UnknownValue = "follow"
    audio_duration: int = Field(default=0, ge=0)
    params: dict[str, object] | None = None

    @property
    def start_frame(self) -> int | None:
        return None if self.cut_frame is None else self.cut_frame - self.left_frames


class ResolvedTrack(CamelModel):
    id: TrackId
    kind: Literal["video", "audio"]
    clips: list[ResolvedClip] = Field(default_factory=list)


class ResolvedMarker(CamelModel):
    marker_id: str
    frame: int
    note: str = ""
    color: str | None = None
    item_id: str | None = None


class TimelineWarning(CamelModel):
    code: str
    """e.g. ``dormant_transition``, ``insufficient_handles``, ``overlay_clamped``,
    ``missing_asset``, ``unknown_transition_type``."""
    message: str
    item_id: str | None = None
    transition_id: str | None = None
    beat_id: str | None = None


class BeatSpan(CamelModel):
    """Where a beat's visible content sits on the main line (overlay anchors)."""

    beat_id: str
    start: int
    duration: int


class ResolvedTimeline(CamelModel):
    project_id: str
    revision: int
    rate: Rational
    width: int
    height: int
    sample_rate: int
    duration: int = Field(ge=0)
    """Total frames of the main line."""
    tracks: list[ResolvedTrack] = Field(default_factory=list)
    transitions: list[ResolvedTransition] = Field(default_factory=list)
    """Active transitions in timeline order."""
    dormant_transitions: list[ResolvedTransition] = Field(default_factory=list)
    beats: list[BeatSpan] = Field(default_factory=list)
    markers: list[ResolvedMarker] = Field(default_factory=list)
    warnings: list[TimelineWarning] = Field(default_factory=list)

    def track(self, track_id: str) -> ResolvedTrack | None:
        return next((t for t in self.tracks if t.id == track_id), None)
