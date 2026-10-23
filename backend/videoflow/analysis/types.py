"""Analysis contracts: derived, cached, rebuildable data (never stored in project.json).

Times are integer microseconds of the asset's source time. Segment and shot ids are
opaque (``seg_<ULID>``): their bounds live in the segment records, never in the id. After
re-segmentation, old ids are mapped to new ones by IoU >= 0.5 (:class:`SegmentRemap`);
unmatched TakeRefs get ``needsRelink``.

Scores, flags and alignment offsets (:class:`TakeAnalysis`) live here and are joined with
the project's TakeRefs when read.
"""

from typing import Annotated, Any, Literal

from pydantic import Field

from videoflow.core.base import CamelModel, UnknownValue
from videoflow.core.time import Micros, NonNegativeMicros, TimeRange

type SegmentKindName = Literal["speech", "visual"]
SegmentKind = Annotated[SegmentKindName | UnknownValue, Field(union_mode="left_to_right")]

type RelationKindName = Literal["retake", "partial_retake", "visual_duplicate", "simultaneous"]
RelationKind = Annotated[RelationKindName | UnknownValue, Field(union_mode="left_to_right")]

type TakeFlagName = Literal["false_start", "off_topic", "fillers", "clipped_audio", "last_take"]
TakeFlag = Annotated[TakeFlagName | UnknownValue, Field(union_mode="left_to_right")]

type BeatRoleName = Literal["intro", "content", "transition", "outro", "off_topic"]
BeatRole = Annotated[BeatRoleName | UnknownValue, Field(union_mode="left_to_right")]


class EngineInfo(CamelModel):
    """Identity of an engine run; part of every stage cache key."""

    engine_id: str
    model_id: str
    version: str = "1"
    device: str = "cpu"
    """Execution device actually used (npu / gpu / cpu), for reporting."""


# --------------------------------------------------------------------------- words


class Word(CamelModel):
    text: str
    start_us: Micros
    end_us: Micros
    prob: float | None = None
    """Engine confidence when the engine provides one (Parakeet does not)."""


class Transcript(CamelModel):
    asset_id: str | None = None
    language: str | None = None
    words: list[Word] = Field(default_factory=list)
    engine: EngineInfo | None = None


class SpeechRanges(CamelModel):
    asset_id: str | None = None
    ranges: list[TimeRange] = Field(default_factory=list)
    engine: EngineInfo | None = None


class Shot(CamelModel):
    id: str
    asset_id: str
    index: int = Field(ge=0)
    start_us: NonNegativeMicros
    end_us: NonNegativeMicros


# --------------------------------------------------------------------------- segments


class Utterance(CamelModel):
    """Consecutive words without a long gap; the unit of segmentation (08 §3, 04 S9)."""

    asset_id: str
    start_us: Micros
    end_us: Micros
    word_start: int = Field(ge=0)
    """Index of the first word in the asset transcript."""
    word_end: int = Field(ge=0)
    """Index one past the last word."""
    text: str


class Segment(CamelModel):
    """One attempt at saying something (speech) or a non-speech shot range (visual)."""

    id: str
    asset_id: str
    kind: SegmentKind
    start_us: Micros
    end_us: Micros
    text: str = ""
    word_start: int | None = None
    word_end: int | None = None
    utterance_count: int = 0
    shot_ids: list[str] = Field(default_factory=list)

    @property
    def range(self) -> TimeRange:
        return TimeRange(start_us=self.start_us, end_us=self.end_us)


class SegmentRemap(CamelModel):
    """Old segment id -> new segment id after re-segmentation (IoU >= threshold)."""

    mapping: dict[str, str] = Field(default_factory=dict)
    iou: dict[str, float] = Field(default_factory=dict)
    unmatched: list[str] = Field(default_factory=list)
    threshold: float = 0.5


# --------------------------------------------------------------------------- relations


class RelationScores(CamelModel):
    text_sim: float | None = None
    lex: float | None = None
    cosine: float | None = None
    cov_a: float | None = None
    cov_b: float | None = None
    vis_sim: float | None = None
    psr: float | None = None
    """Peak-to-sidelobe ratio (sync)."""
    offset_us: Micros | None = None
    """b time - a time for aligned content (sync and alignment)."""
    drift_ppm: float | None = None


class Relation(CamelModel):
    a: str
    b: str
    kind: RelationKind
    score: float
    """Edge weight in [0, 1] used by clustering."""
    scores: RelationScores = Field(default_factory=RelationScores)
    details: dict[str, Any] = Field(default_factory=dict)


class SyncResult(CamelModel):
    """Asset-level offset between two simultaneous recordings."""

    asset_a: str
    asset_b: str
    offset_us: Micros
    """Asset b time + offset = asset a time."""
    drift_ppm: float = 0.0
    psr: float
    accepted: bool


# --------------------------------------------------------------------------- takes


class TakeAnalysis(CamelModel):
    """Derived per-take data joined with ``TakeRef`` at read time."""

    segment_id: str
    score: float | None = None
    breakdown: dict[str, float] = Field(default_factory=dict)
    flags: list[TakeFlag] = Field(default_factory=list)
    align_offset_us: Micros | None = None
    """Display offset relative to the beat's selected take."""


class AlignmentAnchor(CamelModel):
    ref_us: Micros
    take_us: Micros


class TakeAlignment(CamelModel):
    reference_segment_id: str
    segment_id: str
    offset_us: Micros
    anchors: list[AlignmentAnchor] = Field(default_factory=list)
    divergences: list[TimeRange] = Field(default_factory=list)


# --------------------------------------------------------------------------- proposals


class ProposedBeat(CamelModel):
    key: str
    """Stable within one run; reconcile() matches proposals to project beats by overlap."""
    kind: SegmentKind
    segment_ids: list[str]
    label: str = ""
    summary: str | None = None
    role: BeatRole = "content"
    best_segment_id: str | None = None
    reason: str | None = None
    label_source: Literal["llm", "tfidf", "user"] | UnknownValue = "tfidf"


class Proposal(CamelModel):
    """Output of S12-S16 for one run: proposed beats in story order, plus the edges."""

    run_id: str
    pipeline_version: str
    params: dict[str, Any] = Field(default_factory=dict)
    beats: list[ProposedBeat] = Field(default_factory=list)
    edges: list[Relation] = Field(default_factory=list)
    orphans: list[str] = Field(default_factory=list)
    takes: list[TakeAnalysis] = Field(default_factory=list)


class ThresholdProfile(CamelModel):
    """Per-embedding-model thresholds (08 H15: absolute cosine values are model-specific)."""

    model_id: str
    query_prefix: str = ""
    """Prefix the model expects on inputs (e5: ``"query: "``)."""
    prefilter_top_k: int = Field(default=10, gt=0)
    cosine_floor: float = Field(default=0.0, ge=0.0, lt=1.0)
    """Cosine of unrelated texts for this model; cosines are rescaled from
    ``[floor, 1]`` to ``[0, 1]`` before being mixed with lexical scores (e5 ~0.8)."""
    theta_text: float = 0.55
    min_coverage: float = 0.5
    partial_coverage: float = 0.8
    partial_max_ratio: float = 0.6
    lex_weight: float = 0.6
    theta_vis: float = 0.85
    tau: float = 0.5
    """Clustering distance threshold at sensitivity 0.5."""


# --------------------------------------------------------------------------- LLM labels


class LabelTakeInput(CamelModel):
    take_id: str
    """The segment id."""
    duration_us: NonNegativeMicros
    text: str
    heuristic_flags: list[str] = Field(default_factory=list)


class BeatLabelRequest(CamelModel):
    language: str
    beat_key: str
    previous_label: str | None = None
    next_label: str | None = None
    takes: list[LabelTakeInput]


class LabelTakeOutput(CamelModel):
    take_id: str
    false_start: bool = False
    off_topic: bool = False
    note: str = Field(default="", max_length=80)


class BeatLabelResult(CamelModel):
    label: str = Field(max_length=48)
    summary: str = Field(default="", max_length=160)
    role: BeatRole = "content"
    takes: list[LabelTakeOutput] = Field(default_factory=list)
    best_take_id: str | None = None
    reason: str = Field(default="", max_length=120)
