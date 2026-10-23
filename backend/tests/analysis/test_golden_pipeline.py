"""Golden run of S9-S16 on the WP4 retake scripts (FR/EN word fixtures), then reconcile."""

import pytest

from videoflow.analysis import cluster, segment
from videoflow.analysis.labels_tfidf import tfidf_labels
from videoflow.analysis.order import SegmentClock, order_beats, select_default
from videoflow.analysis.reconcile import reconcile
from videoflow.analysis.relations import (
    compute_relations,
    embedding_input,
    prepare_tokens,
    profile_for,
)
from videoflow.analysis.score import TakeFeatures, false_start_ids, score_beat
from videoflow.analysis.types import Proposal, ProposedBeat, Segment
from videoflow.engines.protocols import FakeTextEmbedder
from videoflow.project.models import Asset, AssetProbe, Project
from videoflow.samples import SCRIPTS

from .wordfix import id_factory, retake_script, words_for

EXPECTED_LABEL = {"fr": "Assembler video partir", "en": "Assemble video rushes"}


def run(lang: str, sensitivity: float = 0.5) -> tuple[Proposal, dict[str, Segment]]:
    words = words_for(retake_script(lang))
    utts = segment.split_utterances(words, "ast_1", lang)
    segs = segment.segment_speech(words, utts, "ast_1", lang, new_id=id_factory())
    embedder = FakeTextEmbedder()
    profile = profile_for(embedder.model_id)
    vecs = embedder.encode([embedding_input(s.text, profile) for s in segs], role="query")
    tokens = prepare_tokens(segs, {"ast_1": words}, lang)
    rels = compute_relations(segs, tokens, profile, dict(zip([s.id for s in segs], vecs,
                                                             strict=True)))  # fmt: skip
    assert rels.splits == []
    tau = cluster.tau_for_sensitivity(sensitivity, profile)
    clusters = cluster.cluster([s.id for s in segs], {s.id: str(s.kind) for s in segs},
                               rels.relations, tau).clusters  # fmt: skip
    by_id = {s.id: s for s in segs}
    fs = false_start_ids(rels.relations, tokens)
    orphans = cluster.find_orphans(clusters, by_id, false_starts=fs)
    labels = tfidf_labels(
        {str(k): [by_id[m].text for m in c] for k, c in enumerate(clusters)}, lang
    )
    beats: list[ProposedBeat] = []
    takes = []
    for k, members in enumerate(clusters):
        if members[0] in orphans:
            continue
        feats = [
            TakeFeatures(m, tokens[m], false_start=m in fs, recorded_at_us=by_id[m].start_us,
                         mean_prob=0.9)
            for m in members
        ]  # fmt: skip
        scored = score_beat(feats)
        takes += scored
        best = select_default(scored, recorded_at={m: by_id[m].start_us for m in members})
        beats.append(ProposedBeat(key=f"k{k}", kind="speech", segment_ids=members,
                                  label=labels[str(k)], best_segment_id=best))  # fmt: skip
    clocks = {s.id: SegmentClock(s.id, "retake.mp4", s.start_us, 1_000 + s.start_us) for s in segs}
    ordered = order_beats(beats, clocks, fs).beats
    proposal = Proposal(run_id="run_1", pipeline_version="1", beats=ordered,
                        edges=rels.relations, orphans=orphans, takes=takes)  # fmt: skip
    return proposal, by_id


@pytest.mark.parametrize("lang", ["fr", "en"])
def test_retake_script_golden(lang: str) -> None:
    proposal, segs = run(lang)
    # 4 segments: false start + 3 takes; the takes form the expected beat (manifest:
    # expected_beats[0].take_ids = t1..t3, best = last take)
    assert [s.text for s in segs.values()] == retake_script(lang)
    assert [(b.segment_ids, b.best_segment_id, b.label) for b in proposal.beats] == [
        (["seg_002", "seg_003", "seg_004"], "seg_004", EXPECTED_LABEL[lang])
    ]
    assert proposal.orphans == ["seg_001"]
    assert segs["seg_002"].text == SCRIPTS[lang]["take"]
    assert {(e.a, e.b, e.kind) for e in proposal.edges} == {
        ("seg_002", "seg_003", "retake"),
        ("seg_002", "seg_004", "retake"),
        ("seg_003", "seg_004", "retake"),
    }
    t = {x.segment_id: x for x in proposal.takes}
    assert t["seg_004"].flags == ["last_take"]


def _project(segs: dict[str, Segment]) -> Project:
    asset = Asset(id="ast_1", path="/media/retake.mp4", content_hash="h",
                  probe=AssetProbe(duration_us=60_000_000))  # fmt: skip
    return Project(id="prj_1", name="p", assets=[asset])


def test_reconcile_creates_then_keeps_locked_beats() -> None:
    proposal, segs = run("fr")
    project = _project(segs)
    new_beat, new_clip = id_factory("beat"), id_factory("clip")
    p1, rep = reconcile(project, proposal, segs, new_beat, new_clip)
    assert rep.created == {"k1": "beat_001"}
    (beat,) = p1.beats
    assert [t.segment_id for t in beat.takes] == ["seg_002", "seg_003", "seg_004"]
    assert beat.selected_take is not None and beat.selected_take.segment_id == "seg_004"
    pad = p1.settings.clip_padding
    assert beat.cut[0].source_in_us == segs["seg_004"].start_us - pad.before_us
    assert not beat.locked

    # re-run unchanged: the unlocked beat is matched and keeps its id and cut
    p2, rep = reconcile(p1, proposal, segs, new_beat, new_clip)
    assert rep.updated == {"beat_001": "k1"} and rep.created == {}
    assert p2.beats[0].cut == p1.beats[0].cut

    # user locks the beat with only two takes; a new proposal groups all four
    p2.beats[0].locked = True
    p2.beats[0].takes = p2.beats[0].takes[:2]
    loose = proposal.model_copy(deep=True)
    loose.beats[0].segment_ids = ["seg_001", "seg_002", "seg_003", "seg_004"]
    p3, rep = reconcile(p2, loose, segs, new_beat, new_clip)
    assert rep.kept_locked == ["beat_001"]
    assert p3.beats[0] == p2.beats[0]
    assert [b.id for b in p3.beats] == ["beat_001", "beat_002"]
    assert [t.segment_id for t in p3.beats[1].takes] == ["seg_001", "seg_004"]
    assert sorted(rep.withdrawn) == ["seg_002", "seg_003"]


def test_reconcile_removes_unmatched_and_respects_dismissed() -> None:
    proposal, segs = run("en")
    project = _project(segs)
    p1, _ = reconcile(project, proposal, segs, id_factory("beat"), id_factory("clip"))
    p1.overrides.dismissed_segment_ids = ["seg_004"]
    empty = proposal.model_copy(update={"beats": []})
    p2, rep = reconcile(p1, empty, segs, id_factory("x"), id_factory("y"))
    assert p2.beats == [] and rep.removed == ["beat_001"]
    p3, rep = reconcile(p1, proposal, segs, id_factory("x"), id_factory("y"))
    assert [t.segment_id for t in p3.beats[0].takes] == ["seg_002", "seg_003"]
    assert "seg_004" in rep.withdrawn
