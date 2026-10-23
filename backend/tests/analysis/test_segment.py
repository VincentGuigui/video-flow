from videoflow.analysis import segment
from videoflow.analysis.segment import SegmentationParams
from videoflow.analysis.types import Segment, Shot
from videoflow.core.time import TimeRange

from .wordfix import id_factory, retake_script, words_for


def test_retake_script_fr_golden() -> None:
    words = words_for(retake_script("fr"))
    utts = segment.split_utterances(words, "ast_1", "fr")
    assert [(u.word_start, u.word_end) for u in utts] == [(0, 6), (6, 16), (16, 26), (26, 36)]
    segs = segment.segment_speech(words, utts, "ast_1", "fr", new_id=id_factory())
    assert [(s.id, s.word_start, s.word_end, s.utterance_count) for s in segs] == [
        ("seg_001", 0, 6, 1),
        ("seg_002", 6, 16, 1),
        ("seg_003", 16, 26, 1),
        ("seg_004", 26, 36, 1),
    ]
    assert segs[0].text == "alors dans la... attends je reprends"
    assert segs[1].start_us == words[6].start_us and segs[1].end_us == words[15].end_us


def test_retake_script_en_golden() -> None:
    words = words_for(retake_script("en"))
    utts = segment.split_utterances(words, "ast_1", "en")
    segs = segment.segment_speech(words, utts, "ast_1", "en", new_id=id_factory())
    assert [s.text for s in segs] == retake_script("en")


def test_restart_without_gap_rule_uses_any_utterance_start() -> None:
    # Gaps of 1 s never close a block (2 s rule); the restart check must catch the retake
    # even when the block already holds two utterances (08 H13).
    utt = [
        "today we are going to assemble the video",
        "it will take ten minutes",
        "today we are going to assemble the video",
        "it will take ten minutes",
    ]
    words = words_for(utt)
    utts = segment.split_utterances(words, "a", "en")
    segs = segment.segment_speech(words, utts, "a", "en", new_id=id_factory())
    assert [s.utterance_count for s in segs] == [2, 2]
    # the second utterance of the retake restarts on the block's *second* utterance
    utt2 = [utt[0], utt[1], utt[1], "and then we export"]
    words2 = words_for(utt2)
    segs2 = segment.segment_speech(
        words2, segment.split_utterances(words2, "a", "en"), "a", "en", new_id=id_factory()
    )
    assert [s.utterance_count for s in segs2] == [2, 2]


def test_restart_cue_inside_utterance_splits_false_start() -> None:
    text = "so in the wait let me start over today we are going to assemble the video"
    words = words_for([text])
    utts = segment.split_utterances(words, "a", "en")
    assert [u.text for u in utts] == [
        "so in the wait let me start over",
        "today we are going to assemble the video",
    ]
    segs = segment.segment_speech(words, utts, "a", "en", new_id=id_factory())
    assert len(segs) == 2


def test_gap_rules_and_shot_boundary() -> None:
    words = words_for(["one two three.", "four five", "six seven", "eight"],
                      gaps_us=[500_000, 300_000, 900_000])  # fmt: skip
    utts = segment.split_utterances(words, "a", "en")
    # sentence end + 0.5 s gap splits; 0.3 s does not; 0.9 s splits
    assert [u.text for u in utts] == ["one two three.", "four five six seven", "eight"]
    shots = [
        Shot(id="shot_1", asset_id="a", index=0, start_us=0, end_us=words[6].end_us + 100_000),
        Shot(id="shot_2", asset_id="a", index=1, start_us=words[6].end_us + 100_000,
             end_us=60_000_000),
    ]  # fmt: skip
    segs = segment.segment_speech(words, utts, "a", "en", shots=shots, new_id=id_factory())
    assert [s.utterance_count for s in segs] == [2, 1]  # cut inside the 0.9 s gap
    assert [s.shot_ids for s in segs] == [["shot_1"], ["shot_2"]]
    params = SegmentationParams(block_gap_us=400_000)
    segs = segment.segment_speech(words, utts, "a", "en", params=params, new_id=id_factory())
    assert len(segs) == 3


def test_segment_visual_and_split() -> None:
    shots = [Shot(id="s1", asset_id="a", index=0, start_us=0, end_us=50_000_000)]
    speech = [TimeRange(start_us=1_000_000, end_us=2_000_000),
              TimeRange(start_us=3_000_000, end_us=8_000_000)]  # fmt: skip
    segs = segment.segment_visual(shots, speech, "a", new_id=id_factory())
    # [0,1) too short, [2,3) too short, [8, 50) = 42 s -> 3 pieces of 14 s
    assert [(s.start_us, s.end_us) for s in segs] == [
        (8_000_000, 22_000_000),
        (22_000_000, 36_000_000),
        (36_000_000, 50_000_000),
    ]
    assert all(s.kind == "visual" and s.shot_ids == ["s1"] for s in segs)


def test_split_segment_and_remap() -> None:
    words = words_for(["a b c d e f"])
    seg = Segment(
        id="seg_x",
        asset_id="a",
        kind="speech",
        start_us=words[0].start_us,
        end_us=words[-1].end_us,
        text="a b c d e f",
        word_start=0,
        word_end=6,
    )
    parts = segment.split_segment(seg, words, [2, 4], new_id=id_factory("new"))
    assert [(p.word_start, p.word_end, p.text) for p in parts] == [
        (0, 2, "a b"), (2, 4, "c d"), (4, 6, "e f")
    ]  # fmt: skip
    remap = segment.remap_segments([seg], parts)
    assert remap.unmatched == ["seg_x"]  # no piece has IoU >= 0.5
    remap = segment.remap_segments(parts, [seg], threshold=0.3)
    assert remap.mapping == {"new_001": "seg_x", "new_002": "seg_x", "new_003": "seg_x"}
