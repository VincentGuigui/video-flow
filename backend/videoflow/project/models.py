"""Project schema v1: the authored decisions stored in ``project.json``.

Overview
========

``project.json`` holds **decisions only** (08 §1, §3 corrections to 05): what the user
accepted, selected, trimmed, ordered and transitioned. Everything derived (transcripts,
segments, relations, scores, flags, alignment offsets, proposals) lives in the analysis
cache under ``analysis/`` and ``features/`` and is joined at read time.

Conventions
-----------

* JSON keys are camelCase (``model_dump(by_alias=True)``); Python attributes snake_case.
* All times are **integer microseconds** (fields end in ``_us`` / ``Us``); rates are
  rationals (:class:`~videoflow.core.time.Rational`). Frame quantisation happens only in
  the resolved timeline (``videoflow.timeline``), never here.
* Ids are opaque ``<prefix>_<ULID>`` strings (:mod:`videoflow.core.ids`), never reused.
* Forward compatibility: every model keeps unknown fields (``extra='allow'``); enum-like
  fields are open and keep unknown values as :class:`~videoflow.core.base.UnknownValue`.
  ``app.minReader`` is the lowest schema version a reader must understand to *write* the
  file: an older app loads it read-only. ``schemaVersion`` changes go through
  :mod:`videoflow.project.migrations`.

Invariants (checked by :func:`invariant_violations`; commands preserve them)
---------------------------------------------------------------------------

1. Ids are unique per entity kind: assets, sync groups, beats, clip items (across all
   beats), transitions, overlays, constraints, markers, transcript edits.
2. References resolve: ``TakeRef.asset_id``, ``ClipItem.asset_id``,
   ``ClipItem.audio.replacement.asset_id``, ``ClipItem.angle_asset_id``,
   ``OverlayItem.asset_id`` and sync group members point to existing assets; a beat
   anchor points to an existing beat.
3. Source ranges are well formed: ``0 <= source_in_us < source_out_us`` for clip items and
   overlays.
4. Within a beat, ``TakeRef.segment_id`` is unique and **at most one** take has
   ``status == "selected"``. A take is *used* when a ``cut`` item carries its segment id;
   ``used`` is derived from ``cut[]`` and never stored. ``selected`` only changes through
   ``PromoteTake``, which rebuilds ``cut``.
5. The **main line** (V1 + A1) is not stored: it is the concatenation of ``beat.cut`` for
   every beat with ``included``, in array order, skipping items with ``enabled=False``
   (``enabled=False`` means removed with ripple; the item is kept so undo and re-enable
   work).
6. A transition sits on the cut after ``after_item_id`` and expects ``before_item_id``
   next. It is **active** only when both items are on the main line and adjacent there;
   otherwise it is **dormant**: kept, never deleted implicitly, compiled as a hard cut
   with a warning. ``after_item_id`` is unique among transitions.
7. Blade: the left part keeps the item id, the right part gets a new id, and a transition
   on the cut after the original item moves to the right part. Promote: the new cut item
   gets a new id, keeps the previous audio settings, resets trims to the take range plus
   padding, and transitions on the beat's outer edges are re-attached to it.
8. Overlays (V2; A2 is P1) anchor either to a beat (``offset_us`` from the beat's visible
   start on the main line, so they follow reorders and trims; clamped by the resolver) or
   to absolute project time.
9. An asset belongs to at most one sync group; offsets live on the group members.
10. Any user decision on a beat sets ``locked=True`` so re-clustering keeps it as is.
"""

from typing import Annotated, Any, Literal

from pydantic import Field, model_validator

from videoflow import __version__
from videoflow.core import ids
from videoflow.core.base import CamelModel, UnknownValue
from videoflow.core.time import Micros, NonNegativeMicros, Rational, TimeRange

SCHEMA_VERSION = 1
"""Schema version this code writes and fully understands."""

type Id = Annotated[str, Field(min_length=1)]


type BeatRoleName = Literal["intro", "content", "transition", "outro", "off_topic"]
type BeatKindName = Literal["speech", "visual"]
type TakeStatusName = Literal["selected", "alternate", "rejected"]
type AudioModeName = Literal["linked", "replaced", "muted"]
type OverlayAudioModeName = Literal["muted", "mix"]
type TrackName = Literal["V2", "A2"]
type TransitionTypeName = Literal[
    "cut",
    "dissolve",
    "dip_black",
    "dip_white",
    "wipe_left",
    "wipe_right",
    "wipe_up",
    "wipe_down",
    "slide_left",
    "slide_right",
    "slide_up",
    "slide_down",
    "smooth_left",
    "smooth_right",
    "smooth_up",
    "smooth_down",
    "circle_open",
    "circle_close",
    "radial",
    "zoom_in",
    "pixelize",
    "noise_dissolve",
    "custom_expr",
]
type AlignmentName = Literal["center", "start", "end"]
type HdrName = Literal["none", "hlg", "pq"]
type ConstraintTypeName = Literal["must_link", "cannot_link"]
type LlmProviderName = Literal["none", "local", "anthropic"]
type FitName = Literal["fill", "fit"]

BeatRole = Annotated[BeatRoleName | UnknownValue, Field(union_mode="left_to_right")]
BeatKind = Annotated[BeatKindName | UnknownValue, Field(union_mode="left_to_right")]
TakeStatus = Annotated[TakeStatusName | UnknownValue, Field(union_mode="left_to_right")]
AudioMode = Annotated[AudioModeName | UnknownValue, Field(union_mode="left_to_right")]
OverlayAudioMode = Annotated[OverlayAudioModeName | UnknownValue, Field(union_mode="left_to_right")]
Track = Annotated[TrackName | UnknownValue, Field(union_mode="left_to_right")]
TransitionType = Annotated[TransitionTypeName | UnknownValue, Field(union_mode="left_to_right")]
Alignment = Annotated[AlignmentName | UnknownValue, Field(union_mode="left_to_right")]
Hdr = Annotated[HdrName | UnknownValue, Field(union_mode="left_to_right")]
ConstraintType = Annotated[ConstraintTypeName | UnknownValue, Field(union_mode="left_to_right")]
LlmProvider = Annotated[LlmProviderName | UnknownValue, Field(union_mode="left_to_right")]


# --------------------------------------------------------------------------- settings


class LoudnessTarget(CamelModel):
    integrated: float = -14.0
    true_peak: float = -1.0


class ClipPadding(CamelModel):
    """Padding added around a take's word range when it becomes a cut item."""

    before_us: NonNegativeMicros = 150_000
    after_us: NonNegativeMicros = 300_000


class DefaultTransition(CamelModel):
    type: TransitionType = "dissolve"
    duration_us: NonNegativeMicros = 500_000


class GroupingSettings(CamelModel):
    sensitivity: float = Field(default=0.5, ge=0.0, le=1.0)
    weights: dict[str, float] | None = None


class ProjectSettings(CamelModel):
    width: int = Field(default=1920, gt=0)
    height: int = Field(default=1080, gt=0)
    frame_rate: Rational = Field(default_factory=lambda: Rational(num=30, den=1))
    sample_rate: int = Field(default=48_000, gt=0)
    language: str = "fr"
    loudness_target: LoudnessTarget = Field(default_factory=LoudnessTarget)
    clip_padding: ClipPadding = Field(default_factory=ClipPadding)
    default_transition: DefaultTransition = Field(default_factory=DefaultTransition)
    grouping: GroupingSettings = Field(default_factory=GroupingSettings)
    llm_provider: LlmProvider = "none"


class AppStamp(CamelModel):
    """Who wrote the file and the minimum schema version needed to write it back."""

    writer: str = Field(default_factory=lambda: f"videoflow {__version__}")
    min_reader: int = Field(default=SCHEMA_VERSION, ge=1)


# --------------------------------------------------------------------------- assets


class VideoStreamInfo(CamelModel):
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    rotation: Literal[0, 90, 180, 270] = 0
    frame_rate: Rational
    vfr: bool = False
    hdr: Hdr = "none"
    codec: str | None = None


class AudioStreamInfo(CamelModel):
    index: int = Field(ge=0)
    channels: int = Field(gt=0)
    sample_rate: int = Field(gt=0)
    codec: str | None = None
    language: str | None = None


class AssetProbe(CamelModel):
    duration_us: NonNegativeMicros
    video: VideoStreamInfo | None = None
    audio_streams: list[AudioStreamInfo] = Field(default_factory=list)
    creation_time: str | None = None
    creation_time_reliable: bool = False

    @property
    def has_audio(self) -> bool:
        return bool(self.audio_streams)


class Asset(CamelModel):
    id: Id
    path: str
    """Absolute path to the source media (never modified)."""
    rel_path: str | None = None
    """Path relative to the bundle's parent folder, used to relink moved media."""
    content_hash: str
    probe: AssetProbe


class SyncMember(CamelModel):
    asset_id: Id
    offset_us: Micros = 0
    """Asset time + offset = group reference clock."""
    drift_ppm: float = 0.0


class SyncGroup(CamelModel):
    """Simultaneous recordings of the same moment (multicam / external audio)."""

    id: Id
    label: str | None = None
    members: list[SyncMember] = Field(default_factory=list)


# --------------------------------------------------------------------------- beats


class TakeRef(CamelModel):
    """A segment proposed or accepted as a take of a beat. Scores/flags are not stored."""

    segment_id: Id
    asset_id: Id
    range: TimeRange
    """Segment bounds at grouping time (word range, no padding)."""
    status: TakeStatus = "alternate"
    needs_relink: bool = False
    """Set when re-segmentation found no segment with IoU >= 0.5 for ``segment_id``."""


class AudioReplacement(CamelModel):
    asset_id: Id
    source_in_us: NonNegativeMicros


class ClipAudio(CamelModel):
    mode: AudioMode = "linked"
    replacement: AudioReplacement | None = None
    gain_db: float = 0.0
    fade_in_us: NonNegativeMicros = 0
    fade_out_us: NonNegativeMicros = 0


class ClipItem(CamelModel):
    """A main-line (V1 + A1) item: a source range of one asset."""

    id: Id
    asset_id: Id
    segment_id: Id | None = None
    """Provenance: the take this item was built from, if any."""
    source_in_us: NonNegativeMicros
    source_out_us: NonNegativeMicros
    enabled: bool = True
    """False = removed from the main line with ripple (kept for undo / re-enable)."""
    audio: ClipAudio = Field(default_factory=ClipAudio)
    angle_asset_id: Id | None = None
    """Sync groups: which camera asset is shown for this item (Phase 2 UI)."""

    @model_validator(mode="after")
    def _range(self) -> "ClipItem":
        if self.source_out_us <= self.source_in_us:
            raise ValueError("source_out_us must be > source_in_us")
        return self

    @property
    def duration_us(self) -> Micros:
        return self.source_out_us - self.source_in_us


class Beat(CamelModel):
    id: Id
    label: str = ""
    summary: str | None = None
    role: BeatRole = "content"
    kind: BeatKind = "speech"
    included: bool = True
    locked: bool = False
    takes: list[TakeRef] = Field(default_factory=list)
    cut: list[ClipItem] = Field(default_factory=list)
    """What this beat contributes to the main line, in order (usually one item)."""

    def take(self, segment_id: str) -> TakeRef | None:
        return next((t for t in self.takes if t.segment_id == segment_id), None)

    @property
    def selected_take(self) -> TakeRef | None:
        return next((t for t in self.takes if t.status == "selected"), None)


# --------------------------------------------------------------------------- transitions


class CrossfadeAudio(CamelModel):
    type: Literal["crossfade"] = "crossfade"
    duration_us: NonNegativeMicros


type TransitionAudio = Annotated[
    Literal["follow", "cut"] | CrossfadeAudio | UnknownValue, Field(union_mode="left_to_right")
]


class Transition(CamelModel):
    """Transition on the main-line cut after ``after_item_id``.

    Active only while ``before_item_id`` directly follows ``after_item_id`` on the main
    line; dormant otherwise (kept, compiled as a hard cut with a warning).
    """

    id: Id
    after_item_id: Id
    before_item_id: Id
    type: TransitionType = "dissolve"
    duration_us: NonNegativeMicros = 500_000
    alignment: Alignment = "center"
    audio: TransitionAudio = "follow"
    params: dict[str, Any] | None = None


# --------------------------------------------------------------------------- overlays


class BeatAnchor(CamelModel):
    """Offset from the anchored beat's visible start on the main line."""

    type: Literal["beat"] = "beat"
    beat_id: Id
    offset_us: Micros = 0


class ProjectAnchor(CamelModel):
    """Absolute timeline time (does not follow ripple edits)."""

    type: Literal["project"] = "project"
    time_us: NonNegativeMicros = 0


type OverlayAnchor = Annotated[BeatAnchor | ProjectAnchor, Field(discriminator="type")]


class OverlayAudio(CamelModel):
    mode: OverlayAudioMode = "muted"
    gain_db: float = 0.0


class FitRect(CamelModel):
    x: float = 0.0
    y: float = 0.0
    scale: float = Field(default=1.0, gt=0.0)


type OverlayFit = Annotated[
    Literal["fill", "fit"] | FitRect | UnknownValue, Field(union_mode="left_to_right")
]


class OverlayItem(CamelModel):
    id: Id
    track: Track = "V2"
    asset_id: Id
    source_in_us: NonNegativeMicros
    source_out_us: NonNegativeMicros
    anchor: OverlayAnchor
    enabled: bool = True
    audio: OverlayAudio = Field(default_factory=OverlayAudio)
    fit: OverlayFit = "fill"

    @model_validator(mode="after")
    def _range(self) -> "OverlayItem":
        if self.source_out_us <= self.source_in_us:
            raise ValueError("source_out_us must be > source_in_us")
        return self


# --------------------------------------------------------------------------- misc


class GroupingConstraint(CamelModel):
    id: Id
    type: ConstraintType
    a: Id
    """Segment id."""
    b: Id
    created_at: str


class ItemMarkerTarget(CamelModel):
    """``time_us`` is source time of the item's asset."""

    type: Literal["item"] = "item"
    item_id: Id


class AssetMarkerTarget(CamelModel):
    """``time_us`` is source time of the asset."""

    type: Literal["asset"] = "asset"
    asset_id: Id


class TimelineMarkerTarget(CamelModel):
    """``time_us`` is timeline time."""

    type: Literal["timeline"] = "timeline"


type MarkerTarget = Annotated[
    ItemMarkerTarget | AssetMarkerTarget | TimelineMarkerTarget, Field(discriminator="type")
]


class Marker(CamelModel):
    id: Id
    target: MarkerTarget
    time_us: NonNegativeMicros
    note: str = ""
    color: str | None = None


class TranscriptEdit(CamelModel):
    """User correction of the transcript words of ``asset_id`` within a source range."""

    id: Id
    asset_id: Id
    range: TimeRange
    text: str


class Overrides(CamelModel):
    """User overrides applied on top of the analysis cache (survive re-analysis)."""

    transcript_edits: list[TranscriptEdit] = Field(default_factory=list)
    dismissed_segment_ids: list[Id] = Field(default_factory=list)
    """Orphan segments the user dismissed."""


# --------------------------------------------------------------------------- project


class Project(CamelModel):
    schema_version: int = Field(default=SCHEMA_VERSION, ge=1)
    app: AppStamp = Field(default_factory=AppStamp)
    id: Id
    name: str
    revision: int = Field(default=0, ge=0)
    """Incremented on every saved command batch."""
    pipeline_version: str | None = None
    """Analysis pipeline version whose segment ids the takes reference."""
    settings: ProjectSettings = Field(default_factory=ProjectSettings)
    assets: list[Asset] = Field(default_factory=list)
    sync_groups: list[SyncGroup] = Field(default_factory=list)
    beats: list[Beat] = Field(default_factory=list)
    """Ordered: array order = story order."""
    overlays: list[OverlayItem] = Field(default_factory=list)
    transitions: list[Transition] = Field(default_factory=list)
    constraints: list[GroupingConstraint] = Field(default_factory=list)
    markers: list[Marker] = Field(default_factory=list)
    overrides: Overrides = Field(default_factory=Overrides)

    # -- lookups ---------------------------------------------------------------

    def asset(self, asset_id: str) -> Asset | None:
        return next((a for a in self.assets if a.id == asset_id), None)

    def beat(self, beat_id: str) -> Beat | None:
        return next((b for b in self.beats if b.id == beat_id), None)

    def find_item(self, item_id: str) -> tuple[Beat, int] | None:
        """The beat holding cut item ``item_id`` and its index in ``beat.cut``."""
        for beat in self.beats:
            for i, item in enumerate(beat.cut):
                if item.id == item_id:
                    return beat, i
        return None

    def main_line(self) -> list[tuple[Beat, ClipItem]]:
        """Derived main line: enabled cut items of included beats, in story order."""
        return [(b, c) for b in self.beats if b.included for c in b.cut if c.enabled]

    def is_transition_active(self, transition: Transition) -> bool:
        line = [c.id for _, c in self.main_line()]
        try:
            i = line.index(transition.after_item_id)
        except ValueError:
            return False
        return i + 1 < len(line) and line[i + 1] == transition.before_item_id


def new_project(name: str, settings: ProjectSettings | None = None) -> Project:
    return Project(id=ids.new_id(ids.PROJECT), name=name, settings=settings or ProjectSettings())


def invariant_violations(project: Project) -> list[str]:
    """Human-readable list of broken invariants (empty when the project is consistent)."""
    problems: list[str] = []

    def unique(kind: str, values: list[str]) -> None:
        seen: set[str] = set()
        for v in values:
            if v in seen:
                problems.append(f"duplicate {kind} id {v}")
            seen.add(v)

    items = [c for b in project.beats for c in b.cut]
    unique("asset", [a.id for a in project.assets])
    unique("sync group", [g.id for g in project.sync_groups])
    unique("beat", [b.id for b in project.beats])
    unique("clip item", [c.id for c in items])
    unique("transition", [t.id for t in project.transitions])
    unique("overlay", [o.id for o in project.overlays])
    unique("constraint", [c.id for c in project.constraints])
    unique("marker", [m.id for m in project.markers])
    unique("transcript edit", [e.id for e in project.overrides.transcript_edits])
    unique("transition afterItemId", [t.after_item_id for t in project.transitions])

    asset_ids = {a.id for a in project.assets}
    beat_ids = {b.id for b in project.beats}

    def ref(kind: str, value: str | None) -> None:
        if value is not None and value not in asset_ids:
            problems.append(f"{kind} references missing asset {value}")

    for beat in project.beats:
        unique(f"take segment in beat {beat.id}", [t.segment_id for t in beat.takes])
        if sum(1 for t in beat.takes if t.status == "selected") > 1:
            problems.append(f"beat {beat.id} has more than one selected take")
        for take in beat.takes:
            ref(f"take {take.segment_id}", take.asset_id)
        for item in beat.cut:
            ref(f"clip item {item.id}", item.asset_id)
            ref(f"clip item {item.id} angle", item.angle_asset_id)
            if item.audio.replacement is not None:
                ref(f"clip item {item.id} audio", item.audio.replacement.asset_id)
    for overlay in project.overlays:
        ref(f"overlay {overlay.id}", overlay.asset_id)
        if isinstance(overlay.anchor, BeatAnchor) and overlay.anchor.beat_id not in beat_ids:
            problems.append(f"overlay {overlay.id} anchored to missing beat")
    grouped: set[str] = set()
    for group in project.sync_groups:
        for member in group.members:
            ref(f"sync group {group.id}", member.asset_id)
            if member.asset_id in grouped:
                problems.append(f"asset {member.asset_id} in more than one sync group")
            grouped.add(member.asset_id)
    return problems
