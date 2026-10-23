import pytest

from videoflow.analysis.relations import SegmentTokens
from videoflow.analysis.score import (
    DEFAULT_WEIGHTS,
    TakeFeatures,
    completeness,
    consensus,
    false_start_ids,
    score_beat,
)
from videoflow.analysis.types import Relation


def _tok(sid: str, ids: list[int], fillers: int = 0, end_cue: bool = False) -> SegmentTokens:
    return SegmentTokens(
        segment_id=sid, asset_id="a", start_us=0, ids=tuple(ids),
        word_index=tuple(range(len(ids))), end_cue=end_cue,
        filler_count=fillers, word_count=len(ids) + fillers,
    )  # fmt: skip


def test_consensus_from_complete_takes_only() -> None:
    takes = [
        TakeFeatures("t1", _tok("t1", [1, 2, 3, 4, 5]), recorded_at_us=1),
        TakeFeatures("t2", _tok("t2", [1, 2, 3, 4, 5]), recorded_at_us=2),
        TakeFeatures("t3", _tok("t3", [1, 2, 3, 4, 5, 6]), recorded_at_us=3),
        TakeFeatures("fs", _tok("fs", [9, 9, 9]), false_start=True, recorded_at_us=0),
    ]
    cons = consensus(takes)
    assert dict(cons) == {1: 1, 2: 1, 3: 1, 4: 1, 5: 1}
    assert completeness(takes[0], cons) == 1.0
    assert completeness(takes[3], cons) == 0.0


def test_consensus_tie_rule_for_two_takes() -> None:
    old = TakeFeatures("t1", _tok("t1", [1, 2, 3, 7]), recorded_at_us=10)
    new = TakeFeatures("t2", _tok("t2", [1, 2, 3, 4]), recorded_at_us=20)
    cons = consensus([old, new])
    # at exactly half, a token counts when the most recent complete take has it
    assert dict(cons) == {1: 1, 2: 1, 3: 1, 4: 1}
    assert completeness(new, cons) == 1.0 and completeness(old, cons) == 0.75


def test_score_renormalises_missing_metrics() -> None:
    t = TakeFeatures("t1", _tok("t1", [1, 2, 3, 4, 5]), mean_prob=0.8)
    (only,) = score_beat([t])
    # completeness 1, fluency 1, confidence 0.8, recency 1 (single take); no audio/video
    assert set(only.breakdown) == {"completeness", "fluency", "confidence", "recency"}
    w = DEFAULT_WEIGHTS
    expected = (w["completeness"] + w["fluency"] + 0.8 * w["confidence"] + w["recency"]) / (
        w["completeness"] + w["fluency"] + w["confidence"] + w["recency"]
    )
    assert only.score == pytest.approx(expected, abs=1e-6)
    assert 0.0 <= only.score <= 1.0
    # Parakeet: no word probabilities -> confidence dropped, not counted as 0
    (no_prob,) = score_beat([TakeFeatures("t1", _tok("t1", [1, 2]))])
    assert "confidence" not in no_prob.breakdown and no_prob.score == pytest.approx(1.0)


def test_false_start_fillers_clipping_recency_flags() -> None:
    takes = [
        TakeFeatures("fs", _tok("fs", [1, 2], end_cue=True), false_start=True,
                     recorded_at_us=1),
        TakeFeatures("t1", _tok("t1", [1, 2, 3, 4], fillers=3), recorded_at_us=2,
                     clip_ratio=0.01, loudness_lufs=-16.0),
        TakeFeatures("t2", _tok("t2", [1, 2, 3, 4]), recorded_at_us=3,
                     clip_ratio=0.0, loudness_lufs=-16.0),
    ]  # fmt: skip
    fs, t1, t2 = score_beat(takes)
    assert fs.flags == ["false_start"]
    assert t1.flags == ["fillers", "clipped_audio"]
    assert t2.flags == ["last_take"]
    assert t2.score is not None and t1.score is not None and fs.score is not None
    assert t2.score > t1.score > fs.score
    assert t2.breakdown["audio"] == 1.0 and t1.breakdown["audio"] == 0.5


def test_video_metrics_relative_within_beat() -> None:
    takes = [
        TakeFeatures("a", sharpness=100.0, shake=0.5, luma=0.5),
        TakeFeatures("b", sharpness=50.0, shake=1.0, luma=0.9),
    ]
    a, b = score_beat(takes)
    assert a.breakdown["video"] == 1.0 and b.breakdown["video"] == 0.0


def test_false_start_ids_from_relations_and_cues() -> None:
    toks = {"x": _tok("x", [1], end_cue=True), "y": _tok("y", [1, 2])}
    rels = [Relation(a="y", b="z", kind="partial_retake", score=1.0,
                     details={"short": "y", "false_start": True})]  # fmt: skip
    assert false_start_ids(rels, toks) == {"x", "y"}
