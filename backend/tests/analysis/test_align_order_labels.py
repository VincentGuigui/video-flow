import numpy as np

from videoflow.analysis import intra_align, segment
from videoflow.analysis.labels_tfidf import tfidf_labels
from videoflow.analysis.order import SegmentClock, natural_key, order_beats, select_default
from videoflow.analysis.relations import prepare_tokens
from videoflow.analysis.textnorm import Vocab
from videoflow.analysis.types import ProposedBeat, Segment, SyncResult, TakeAnalysis

from .wordfix import id_factory, words_for

TAKE = "today we are going to assemble the video from the rushes"


def test_speech_alignment_anchors_offset_divergences() -> None:
    words = words_for([TAKE, "today we are going to quickly assemble the video from the rushes"])
    segs = segment.segment_speech(
        words, segment.split_utterances(words, "a", "en"), "a", "en", new_id=id_factory()
    )
    ref, take = segs
    toks = prepare_tokens(segs, {"a": words}, "en", Vocab())
    al = intra_align.align_speech(ref, take, toks[ref.id], toks[take.id], words, words)
    assert al.offset_us == ref.start_us - take.start_us
    assert len(al.anchors) == 11
    assert al.anchors[0].ref_us == words[0].start_us
    quickly = words[11 + 5]
    assert quickly.text == "quickly"
    assert [(d.start_us, d.end_us) for d in al.divergences] == [(quickly.start_us, quickly.end_us)]


def test_visual_dtw_and_sync_offsets() -> None:
    rng = np.random.default_rng(3)
    frames = rng.normal(size=(10, 16))
    ref = Segment(id="r", asset_id="a", kind="visual", start_us=0, end_us=5_000_000)
    take = Segment(id="t", asset_id="b", kind="visual", start_us=7_000_000, end_us=11_000_000)
    al = intra_align.align_visual(ref, take, frames, frames[2:])
    # take frame 0 == ref frame 2 -> ref time 1.0 s, take time 7.0 s
    assert al.anchors[0].ref_us - al.anchors[0].take_us == 1_000_000 - 7_000_000
    assert al.offset_us == -6_000_000
    sync = SyncResult(asset_a="a", asset_b="b", offset_us=3_217_000, psr=8.0, accepted=True)
    assert intra_align.align_sync(ref, take, sync).offset_us == 3_217_000
    assert intra_align.align_sync(take, ref, sync).offset_us == -3_217_000


def _beat(key: str, segs: list[str], role: str = "content") -> ProposedBeat:
    return ProposedBeat(key=key, kind="speech", segment_ids=segs, role=role)


def test_order_by_earliest_complete_take_with_intro_outro() -> None:
    beats = [_beat("b1", ["s1", "s2"]), _beat("b2", ["fs", "s3"]), _beat("intro", ["s4"],
             "intro")]  # fmt: skip
    clocks = {
        "s1": SegmentClock("s1", "clip10.mp4", 0, recorded_at_us=500),
        "s2": SegmentClock("s2", "clip10.mp4", 0, recorded_at_us=900),
        "fs": SegmentClock("fs", "clip2.mp4", 0, recorded_at_us=100),
        "s3": SegmentClock("s3", "clip2.mp4", 0, recorded_at_us=600),
        "s4": SegmentClock("s4", "clip3.mp4", 0, recorded_at_us=1000),
    }
    res = order_beats(beats, clocks, false_starts={"fs"})
    assert res.by_recording_time
    assert [b.key for b in res.beats] == ["intro", "b1", "b2"]
    assert res.moved == ["intro"]
    # without creation times: natural file-name order (clip2 < clip3 < clip10)
    undated = {k: SegmentClock(c.segment_id, c.asset_name, c.start_us) for k, c in clocks.items()}
    beats[2] = _beat("b3", ["s4"])
    res = order_beats(beats, undated, false_starts={"fs"})
    assert not res.by_recording_time
    assert [b.key for b in res.beats] == ["b2", "b3", "b1"]
    assert natural_key("clip2") < natural_key("Clip10")


def test_default_selection_tie_breaks() -> None:
    takes = [TakeAnalysis(segment_id="a", score=0.8), TakeAnalysis(segment_id="b", score=0.8),
             TakeAnalysis(segment_id="c", score=0.5)]  # fmt: skip
    assert select_default(takes, llm_best="a", recorded_at={"a": 1, "b": 2}) == "a"
    assert select_default(takes, recorded_at={"a": 1, "b": 2}) == "b"
    assert select_default(takes, llm_best="c") == "b"
    assert select_default([]) is None


def test_tfidf_labels_fr_en() -> None:
    fr = tfidf_labels(
        {
            "b1": ["aujourd'hui nous allons assembler la video a partir des rushes"] * 3,
            "b2": ["dans la boîte on trouve le câble USB-C et le chargeur"],
            "b3": ["euh alors attends je reprends"],
        },
        "fr",
    )
    assert fr == {"b1": "Assembler video partir", "b2": "Boîte trouve câble", "b3": ""}
    en = tfidf_labels({"b1": [TAKE], "b2": ["the box holds the charger and the cable"]}, "en")
    assert en == {"b1": "Assemble video rushes", "b2": "Box holds charger"}
    assert all(len(v) <= 48 for v in fr.values())
