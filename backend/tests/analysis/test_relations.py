import numpy as np

from videoflow.analysis import relations, segment
from videoflow.analysis.relations import (
    compute_relations,
    embedding_input,
    prepare_tokens,
    profile_for,
    rescale_cosine,
    top_k_pairs,
)
from videoflow.analysis.types import Segment, SyncResult, ThresholdProfile
from videoflow.engines.protocols import FakeTextEmbedder

from .wordfix import id_factory, words_for

TAKE_FR = "aujourd'hui nous allons assembler la video a partir des rushes"
INTRO_FR = "bonjour a tous et bienvenue sur la chaine on se retrouve pour une nouvelle emission"
PROFILE = ThresholdProfile(model_id="test")


def _segments(utts: list[str], lang: str, gaps: list[int] | None = None):
    words = words_for(utts, gaps_us=gaps)
    segs = segment.segment_speech(
        words, segment.split_utterances(words, "a", lang), "a", lang, new_id=id_factory()
    )
    return words, segs


def test_profiles_are_per_model() -> None:
    e5 = profile_for("intfloat/multilingual-e5-small")
    assert e5.query_prefix == "query: "
    assert embedding_input("bonjour", e5) == "query: bonjour"
    # e5 scores unrelated texts ~0.8: rescaled below 0.1, while MiniLM 0.8 stays high
    assert rescale_cosine(0.80, e5) < 0.1
    mini = profile_for("sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
    assert rescale_cosine(0.80, mini) > 0.7
    unknown = profile_for("some/new-model")
    assert unknown.model_id == "some/new-model" and unknown.theta_text == 0.55


def test_top_k_prefilter_not_absolute_cosine() -> None:
    rng = np.random.default_rng(0)
    vecs = rng.normal(size=(30, 16)) + 5.0  # all cosines high (e5-like)
    pairs = top_k_pairs(vecs, 3)
    assert all(i < j for i, j, _ in pairs)
    assert len(pairs) <= 30 * 3
    assert len(pairs) < 30 * 29 // 2


def test_identical_takes_are_retakes_with_embeddings() -> None:
    words, segs = _segments([TAKE_FR, TAKE_FR, TAKE_FR], "fr")
    toks = prepare_tokens(segs, {"a": words}, "fr")
    emb = FakeTextEmbedder()
    vecs = emb.encode([embedding_input(s.text, PROFILE) for s in segs])
    res = compute_relations(segs, toks, PROFILE, {s.id: v for s, v in zip(segs, vecs, strict=True)})
    assert [(r.a, r.b, r.kind) for r in res.relations] == [
        ("seg_001", "seg_002", "retake"),
        ("seg_001", "seg_003", "retake"),
        ("seg_002", "seg_003", "retake"),
    ]
    assert all(r.score == 1.0 and r.scores.cov_a == 1.0 for r in res.relations)


def test_prefix_false_start_is_partial_retake() -> None:
    words, segs = _segments(["aujourd'hui nous allons euh", TAKE_FR], "fr")
    assert len(segs) == 2
    toks = prepare_tokens(segs, {"a": words}, "fr")
    res = compute_relations(segs, toks, PROFILE)
    assert len(res.relations) == 1
    rel = res.relations[0]
    assert rel.kind == "partial_retake"
    assert rel.details == {"short": "seg_001", "false_start": True}
    assert rel.scores.cov_a == 1.0
    assert not res.splits


def test_contained_match_splits_longer_segment_not_partial() -> None:
    # One block holds an intro and then the take (no gap): the take recorded alone later
    # is *contained* in it. 08 §3: split the longer segment, no PARTIAL_RETAKE.
    words = words_for([f"{INTRO_FR} {TAKE_FR}", TAKE_FR], gaps_us=[3_000_000])
    segs = segment.segment_speech(
        words, segment.split_utterances(words, "a", "fr"), "a", "fr", new_id=id_factory()
    )
    assert [s.word_end - (s.word_start or 0) for s in segs] == [25, 10]
    toks = prepare_tokens(segs, {"a": words}, "fr")
    res = compute_relations(segs, toks, PROFILE)
    assert res.relations == []
    assert len(res.splits) == 1
    split = res.splits[0]
    assert split.segment_id == "seg_001" and split.matched_with == "seg_002"
    assert split.cut_words == (15,)
    assert words[15].text == "aujourd'hui"

    parts = segment.split_segment(segs[0], words, split.cut_words, new_id=id_factory("p"))
    assert [p.text for p in parts] == [INTRO_FR, TAKE_FR]
    segs2 = [*parts, segs[1]]
    res2 = compute_relations(segs2, prepare_tokens(segs2, {"a": words}, "fr"), PROFILE)
    assert [(r.a, r.b, r.kind) for r in res2.relations] == [("p_002", "seg_002", "retake")]


def test_cue_words_stripped_before_coverage() -> None:
    take = "today we are going to assemble the video from the rushes"
    words, segs = _segments([f"wait let me start over {take}", take], "en")
    toks = prepare_tokens(segs, {"a": words}, "en")
    assert len(toks["seg_001"].ids) == len(toks["seg_002"].ids)
    res = compute_relations(segs, toks, PROFILE)
    assert [r.kind for r in res.relations] == ["retake"]
    assert res.relations[0].scores.cov_a == 1.0


def test_unrelated_texts_no_relation() -> None:
    words, segs = _segments(
        ["today we are going to assemble the video", "the box contains a charger and a cable"],
        "en",
    )
    toks = prepare_tokens(segs, {"a": words}, "en")
    res = compute_relations(segs, toks, PROFILE, {s.id: np.ones(4) for s in segs})
    assert res.relations == []


def _seg(sid: str, kind: str, start: int = 0, end: int = 4_000_000, asset: str = "a") -> Segment:
    return Segment(id=sid, asset_id=asset, kind=kind, start_us=start, end_us=end)


def test_visual_duplicate_only_between_non_speech() -> None:
    rng = np.random.default_rng(1)
    base = rng.normal(size=(8, 32))
    other = rng.normal(size=(8, 32))
    frames = {
        "v1": base,
        "v2": base + 0.01 * rng.normal(size=base.shape),
        "v3": other,
        "s1": base,
        "s2": base,
    }
    segs = [_seg("v1", "visual"), _seg("v2", "visual"), _seg("v3", "visual"),
            _seg("s1", "speech"), _seg("s2", "speech")]  # fmt: skip
    res = compute_relations(segs, {}, PROFILE, frame_embeddings=frames)
    assert [(r.a, r.b, r.kind) for r in res.relations] == [("v1", "v2", "visual_duplicate")]
    assert res.relations[0].scores.vis_sim is not None and res.relations[0].scores.vis_sim > 0.99


def test_same_setup_recorded_on_speech_retakes() -> None:
    take = "today we are going to assemble the video"
    words, segs = _segments([take, take], "en")
    frames = {s.id: np.ones((3, 8)) for s in segs}
    res = compute_relations(segs, prepare_tokens(segs, {"a": words}, "en"), PROFILE,
                            frame_embeddings=frames)  # fmt: skip
    assert res.relations[0].details["same_setup"] == 1.0


def test_simultaneous_from_accepted_sync() -> None:
    segs = [
        _seg("a1", "speech", 10_000_000, 14_000_000, "A"),
        _seg("b1", "speech", 6_800_000, 10_800_000, "B"),
        _seg("b2", "speech", 20_000_000, 22_000_000, "B"),
    ]
    sync = SyncResult(asset_a="A", asset_b="B", offset_us=3_217_000, psr=9.3, accepted=True)
    rels = relations.simultaneous_relations(segs, [sync])
    assert [(r.a, r.b, r.kind) for r in rels] == [("a1", "b1", "simultaneous")]
    assert rels[0].scores.offset_us == -3_217_000
    rejected = sync.model_copy(update={"accepted": False})
    assert relations.simultaneous_relations(segs, [rejected]) == []
