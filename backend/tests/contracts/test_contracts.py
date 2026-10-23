import json
from pathlib import Path

import numpy as np
import pytest
from pydantic import ValidationError

from videoflow.analysis.types import (
    BeatLabelRequest,
    BeatLabelResult,
    LabelTakeInput,
    Proposal,
    ProposedBeat,
    Relation,
    RelationScores,
    Segment,
    ThresholdProfile,
    Transcript,
    Word,
)
from videoflow.api.events import (
    AssetUpdatedEvent,
    EventEnvelope,
    ProjectUpdatedEvent,
    event_adapter,
    parse_event,
)
from videoflow.core.base import is_unknown
from videoflow.core.time import Rational, TimeRange
from videoflow.engines.protocols import (
    ASR_SAMPLE_RATE,
    AsrEngine,
    FakeAsrEngine,
    FakeLlmLabeler,
    FakeShotDetector,
    FakeTextEmbedder,
    FakeVadEngine,
    FakeVisualEmbedder,
    LlmLabeler,
    ShotDetector,
    TextEmbedder,
    VadEngine,
    VisualEmbedder,
    audio_key,
)
from videoflow.jobs.types import Job, JobDoneEvent, JobProgressEvent, JobSpec, Priority
from videoflow.timeline.resolved import (
    ResolvedClip,
    ResolvedTimeline,
    ResolvedTrack,
    ResolvedTransition,
    TimelineWarning,
)


def _tone_with_silence() -> np.ndarray:
    sr = ASR_SAMPLE_RATE
    t = np.arange(sr) / sr
    tone = (0.3 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)
    silence = np.zeros(sr, dtype=np.float32)
    return np.concatenate([silence, tone, silence, tone[: sr // 2]])


def test_fakes_satisfy_protocols() -> None:
    assert isinstance(FakeVadEngine(), VadEngine)
    assert isinstance(FakeAsrEngine(), AsrEngine)
    assert isinstance(FakeTextEmbedder(), TextEmbedder)
    assert isinstance(FakeVisualEmbedder(), VisualEmbedder)
    assert isinstance(FakeShotDetector(), ShotDetector)
    assert isinstance(FakeLlmLabeler(), LlmLabeler)


def test_fake_vad_finds_tones() -> None:
    ranges = FakeVadEngine().speech_ranges(_tone_with_silence(), ASR_SAMPLE_RATE)
    assert len(ranges) == 2
    assert abs(ranges[0].start_us - 1_000_000) <= 30_000
    assert abs(ranges[0].end_us - 2_000_000) <= 30_000
    assert abs(ranges[1].start_us - 3_000_000) <= 30_000


def test_fake_vad_replays_fixture() -> None:
    audio = _tone_with_silence()
    fixed = [TimeRange(start_us=5, end_us=10)]
    assert FakeVadEngine({audio_key(audio): fixed}).speech_ranges(audio, ASR_SAMPLE_RATE) == fixed


def test_fake_asr_replays_by_audio_key(tmp_path: Path) -> None:
    audio = _tone_with_silence()
    words = [
        Word(text="bonjour", start_us=1_000_000, end_us=1_400_000, prob=None),
        Word(text="à", start_us=3_000_000, end_us=3_100_000, prob=0.9),
    ]
    fixture = tmp_path / "asr.json"
    fixture.write_text(
        json.dumps({audio_key(audio): Transcript(language="fr", words=words).dump()}),
        encoding="utf-8",
    )
    engine = FakeAsrEngine.from_fixture(fixture)
    out = engine.transcribe(audio, ASR_SAMPLE_RATE)
    assert [w.text for w in out.words] == ["bonjour", "à"]
    assert out.words[0].prob is None
    assert out.engine is not None and out.engine.engine_id == "fake-asr"
    only_first = engine.transcribe(
        audio, ASR_SAMPLE_RATE, ranges=[TimeRange(start_us=0, end_us=2_000_000)]
    )
    assert [w.text for w in only_first.words] == ["bonjour"]
    assert engine.transcribe(np.zeros(10, np.float32), ASR_SAMPLE_RATE).words == []


def test_fake_text_embedder_follows_lexical_overlap() -> None:
    emb = FakeTextEmbedder()
    vecs = emb.encode(
        [
            "dans la boîte on trouve le câble",
            "dans la boîte on trouve le câble et le chargeur",
            "il fait beau aujourd'hui",
        ]
    )
    assert vecs.shape == (3, 384) and vecs.dtype == np.float32
    assert np.allclose(np.linalg.norm(vecs, axis=1), 1.0, atol=1e-6)
    assert vecs[0] @ vecs[1] > 0.7 > vecs[0] @ vecs[2]
    assert np.array_equal(emb.encode(["x y"]), emb.encode(["x y"]))


def test_fake_visual_embedder_separates_shots() -> None:
    rng = np.random.default_rng(0)
    coarse = rng.integers(0, 255, size=(9, 16, 3))
    base = np.kron(coarse, np.ones((8, 8, 1))).astype(np.uint8)  # blocky 72x128 picture
    near = np.clip(base.astype(int) + 12, 0, 255).astype(np.uint8)
    other = base[::-1, ::-1].copy()
    vecs = FakeVisualEmbedder().encode([base, near, other])
    assert vecs[0] @ vecs[1] > 0.99
    assert vecs[0] @ vecs[2] < vecs[0] @ vecs[1]


def test_fake_shots_and_labeler() -> None:
    shots = FakeShotDetector(
        {"a.mp4": [TimeRange(start_us=0, end_us=1), TimeRange(start_us=1, end_us=5)]}
    )
    out = shots.detect(Path("/x/a.mp4"), "ast_1")
    assert [s.index for s in out] == [0, 1] and out[1].end_us == 5
    request = BeatLabelRequest(
        language="fr",
        beat_key="k1",
        takes=[
            LabelTakeInput(take_id="seg_a", duration_us=4_000_000, text="Alors dans la boîte"),
            LabelTakeInput(
                take_id="seg_b", duration_us=9_000_000, text="Dans la boîte on trouve le câble"
            ),
        ],
    )
    result = FakeLlmLabeler().label(request)
    assert result.best_take_id == "seg_b"
    assert result.label.startswith("Dans la boîte")
    with pytest.raises(ValidationError):
        BeatLabelResult(label="x" * 49)


def test_analysis_types_round_trip() -> None:
    proposal = Proposal(
        run_id="run_1",
        pipeline_version="2026.10.0",
        beats=[ProposedBeat(key="k", kind="speech", segment_ids=["seg_a", "seg_b"], role="hook")],
        edges=[
            Relation(
                a="seg_a",
                b="seg_b",
                kind="retake",
                score=0.8,
                scores=RelationScores(text_sim=0.8, cov_a=0.9, cov_b=0.7),
            )
        ],  # fmt: skip
    )
    data = proposal.dump()
    assert data["beats"][0]["segmentIds"] == ["seg_a", "seg_b"]
    again = Proposal.model_validate(data)
    assert again == proposal and is_unknown(again.beats[0].role)
    seg = Segment(id="seg_a", asset_id="ast", kind="speech", start_us=0, end_us=10)
    assert seg.range == TimeRange(start_us=0, end_us=10)
    assert ThresholdProfile(model_id="intfloat/multilingual-e5-small", query_prefix="query: ")


def test_event_union_parses_every_type() -> None:
    events = [
        JobProgressEvent(job_id="job_1", kind="proxy", progress=0.5).dump(),
        JobDoneEvent(job_id="job_1", kind="proxy", state="succeeded").dump(),
        AssetUpdatedEvent(project_id="prj", asset_id="ast", parts=["proxy"]).dump(),
        ProjectUpdatedEvent(project_id="prj", revision=4).dump(),
    ]
    parsed = [parse_event(e) for e in events]
    assert [type(p).__name__ for p in parsed] == [
        "JobProgressEvent",
        "JobDoneEvent",
        "AssetUpdatedEvent",
        "ProjectUpdatedEvent",
    ]
    assert events[0]["type"] == "job.progress" and "jobId" in events[0]
    env = EventEnvelope(seq=3, event=parsed[3])
    assert EventEnvelope.model_validate(env.dump()) == env
    schema = event_adapter.json_schema(by_alias=True)
    assert set(schema["discriminator"]["mapping"]) == {
        "job.progress",
        "job.done",
        "asset.updated",
        "project.updated",
    }
    with pytest.raises(ValidationError):
        parse_event({"type": "nope"})


def test_job_models() -> None:
    spec = JobSpec(kind="proxy", asset_id="ast", priority=Priority.INGEST)
    job = Job(id="job_1", kind=spec.kind, priority=spec.priority)
    assert job.state == "queued" and not job.done
    assert job.model_copy(update={"state": "cancelled"}).done
    assert Priority.INTERACTIVE < Priority.INGEST < Priority.ANALYSIS


def test_resolved_timeline_round_trip() -> None:
    clip = ResolvedClip(
        item_id="clip_a",
        track="V1",
        asset_id="ast",
        timeline_start=0,
        duration=240,
        source_in_us=10_000_000,
        source_out_us=18_000_000,
        source_in_frame=300,
        handle_after=7,
    )
    tl = ResolvedTimeline(
        project_id="prj",
        revision=1,
        rate=Rational.of(30),
        width=1920,
        height=1080,
        sample_rate=48_000,
        duration=240,
        tracks=[ResolvedTrack(id="V1", kind="video", clips=[clip])],
        transitions=[
            ResolvedTransition(
                transition_id="tr",
                after_item_id="clip_a",
                before_item_id="clip_b",
                type="dissolve",
                state="active",
                duration=15,
                cut_frame=240,
                left_frames=7,
                right_frames=8,
            )
        ],
        warnings=[TimelineWarning(code="dormant_transition", message="m", transition_id="t2")],
    )
    assert ResolvedTimeline.model_validate(tl.dump()) == tl
    assert tl.transitions[0].start_frame == 233
    assert clip.timeline_end == 240
    track = tl.track("V1")
    assert track is not None and track.clips == [clip]
