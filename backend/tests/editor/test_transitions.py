from videoflow.editor.models import EditorClip, EditorDocument, EditorTransition
from videoflow.editor.transitions import plan_transitions


def clip(id, start, source_in=10, length=25, kind="video", layer=0, link=None, asset="a"):
    return EditorClip(
        id=id,
        kind=kind,
        asset_id=asset,
        name=id,
        start=start,
        source_in=source_in,
        source_out=source_in + length,
        layer=layer,
        link_id=link,
    )


def document(*transitions, right_in=10):
    return EditorDocument(
        clips=[
            clip("l", 0, link="p"),
            clip("la", 0, kind="audio", link="p"),
            clip("r", 25, source_in=right_in, link="q", asset="b"),
            clip("ra", 25, source_in=right_in, kind="audio", link="q", asset="b"),
        ],
        transitions=list(transitions),
    )


def frames(_):
    return 100


def test_dissolve_overlaps_clips_using_handles_and_crossfades_audio():
    plan = plan_transitions(
        document(EditorTransition(id="t", left_id="l", right_id="r", duration=10)), frames
    )
    by = {c.id: c for c in plan.clips}
    assert (by["l"].source_out, by["la"].source_out) == (40, 40)
    assert (by["r"].start, by["r"].source_in, by["ra"].start) == (20, 5, 20)
    assert plan.total == 50
    assert plan.video_fade_in == {"r": 10}
    assert plan.audio_fades == {"la": (0, 10), "ra": (10, 0)}
    assert not plan.warnings


def test_missing_head_handle_shortens_the_dissolve_with_a_warning():
    plan = plan_transitions(
        document(EditorTransition(id="t", left_id="l", right_id="r", duration=10), right_in=0),
        frames,
    )
    item = plan.active[0]
    assert (item.before, item.after, item.shortened) == (0, 5, True)
    assert plan.warnings and "shortened" in plan.warnings[0]


def test_dip_needs_no_handles_and_keeps_clips():
    plan = plan_transitions(
        document(
            EditorTransition(id="t", left_id="l", right_id="r", type="dip_white", duration=10),
            right_in=0,
        ),
        frames,
    )
    assert [(c.start, c.source_in, c.source_out) for c in plan.clips] == [
        (0, 10, 35),
        (0, 10, 35),
        (25, 0, 25),
        (25, 0, 25),
    ]
    assert [(d.start, d.before, d.after, d.color) for d in plan.dips] == [(20, 5, 5, "white")]
    assert plan.audio_fades == {"la": (0, 5), "ra": (5, 0)}


def test_dormant_transitions_are_ignored_and_validate():
    plan = plan_transitions(
        document(
            EditorTransition(id="gone", left_id="missing", right_id="r"),
            EditorTransition(id="reverse", left_id="r", right_id="l"),
            EditorTransition(id="audio", left_id="la", right_id="ra"),
        ),
        frames,
    )
    assert plan.active == [] and plan.dips == [] and plan.video_fade_in == {}


def test_edge_fades_are_planned_per_clip_and_capped():
    doc = EditorDocument(
        clips=[
            clip("v", 0, link="p").model_copy(update={"fade_in": 10, "fade_out": 99}),
            clip("a", 0, kind="audio", link="p").model_copy(update={"fade_in": 10, "fade_out": 5}),
        ]
    )
    plan = plan_transitions(doc, frames)
    assert plan.video_fade_in == {"v": 10} and plan.video_fade_out == {"v": 25}
    assert plan.audio_fades == {"a": (10, 5)}


def test_edge_fade_merges_with_a_dissolve():
    doc = document(EditorTransition(id="t", left_id="l", right_id="r", duration=10))
    doc.clips[2] = doc.clips[2].model_copy(update={"fade_in": 4})
    assert plan_transitions(doc, frames).video_fade_in == {"r": 10}
