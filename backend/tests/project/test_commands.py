from collections.abc import Callable

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from tests.project.conftest import load_fixture_dict
from videoflow.core import ids
from videoflow.core.time import TimeRange
from videoflow.project.commands import (
    COMMAND_TYPES,
    AddAsset,
    AddBeat,
    Batch,
    BladeItem,
    Command,
    CommandError,
    MoveBeat,
    MoveTake,
    PromoteTake,
    PutBeat,
    PutConstraint,
    PutMarker,
    PutOverlay,
    PutSyncGroup,
    PutTranscriptEdit,
    PutTransition,
    RelinkAsset,
    RemoveAsset,
    RemoveBeat,
    RemoveConstraint,
    RemoveMarker,
    RemoveOverlay,
    RemoveSyncGroup,
    RemoveTranscriptEdit,
    RemoveTransition,
    RenameProject,
    SetBeatIncluded,
    SetClipAudio,
    SetItemEnabled,
    SetSegmentDismissed,
    SetSettings,
    SetTakeStatus,
    SetTransition,
    TrimItem,
    UpdateBeat,
    apply_batch,
    command_list_adapter,
    parse_command,
)
from videoflow.project.models import (
    Asset,
    AssetProbe,
    Beat,
    BeatAnchor,
    ClipAudio,
    ClipItem,
    GroupingConstraint,
    ItemMarkerTarget,
    OverlayItem,
    Project,
    ProjectAnchor,
    SyncGroup,
    SyncMember,
    TakeRef,
    TranscriptEdit,
    Transition,
    invariant_violations,
)

type Sample = Callable[[Project], tuple[Project, Command]]


def _beat(p: Project, label: str) -> Beat:
    return next(b for b in p.beats if b.label == label)


def _intro(p: Project) -> Beat:
    return _beat(p, "Ouverture")


def _acc(p: Project) -> Beat:
    return _beat(p, "Accessoires dans la boîte")


def _demo(p: Project) -> Beat:
    return _beat(p, "Démo du chargeur")


def _outtake(p: Project) -> Beat:
    return _beat(p, "Hors sujet")


def _new_asset() -> Asset:
    return Asset(
        id=ids.new_id(ids.ASSET),
        path="/media/extra.mov",
        content_hash="xxh3:1234",
        probe=AssetProbe(duration_us=5_000_000),
    )


def _with(p: Project, cmd: Command) -> Project:
    return cmd.apply(p)[0]


SAMPLES: dict[str, Sample] = {
    "RenameProject": lambda p: (p, RenameProject(name="Renamed")),
    "SetSettings": lambda p: (
        p,
        SetSettings(settings=p.settings.model_copy(update={"width": 1280, "height": 720})),
    ),
    "AddAsset": lambda p: (p, AddAsset(asset=_new_asset(), index=1)),
    "RemoveAsset": lambda p: (
        (q := _with(p, AddAsset(asset=_new_asset(), index=2))),
        RemoveAsset(asset_id=q.assets[2].id),
    ),
    "RelinkAsset": lambda p: (
        p,
        RelinkAsset(asset_id=p.assets[0].id, path="/new/IMG_0412.MOV", rel_path=None),
    ),
    "PutSyncGroup": lambda p: (
        p,
        PutSyncGroup(
            group=SyncGroup(
                id=ids.new_id(ids.SYNC_GROUP),
                members=[SyncMember(asset_id=p.assets[1].id), SyncMember(asset_id=p.assets[2].id)],
            ),
            index=0,
        ),
    ),
    "RemoveSyncGroup": lambda p: (p, RemoveSyncGroup(group_id=p.sync_groups[0].id)),
    "AddBeat": lambda p: (
        p,
        AddBeat(
            beat=Beat(
                id=ids.new_id(ids.BEAT),
                label="New",
                cut=[
                    ClipItem(
                        id=ids.new_id(ids.CLIP),
                        asset_id=p.assets[1].id,
                        source_in_us=0,
                        source_out_us=1_000_000,
                    )
                ],
            ),
            index=1,
        ),
    ),
    "RemoveBeat": lambda p: (p, RemoveBeat(beat_id=_outtake(p).id)),
    "PutBeat": lambda p: (
        p,
        PutBeat(beat=_demo(p).model_copy(update={"label": "Changed", "takes": []})),
    ),
    "MoveBeat": lambda p: (p, MoveBeat(beat_id=_demo(p).id, to_index=0)),
    "UpdateBeat": lambda p: (p, UpdateBeat(beat_id=_demo(p).id, label="Relabelled", role="outro")),
    "SetBeatIncluded": lambda p: (p, SetBeatIncluded(beat_id=_outtake(p).id, included=True)),
    "SetTakeStatus": lambda p: (
        p,
        SetTakeStatus(
            beat_id=_acc(p).id, segment_id=_acc(p).takes[1].segment_id, status="rejected"
        ),
    ),
    "MoveTake": lambda p: (
        p,
        MoveTake(
            segment_id=_acc(p).takes[0].segment_id,
            from_beat_id=_acc(p).id,
            to_beat_id=_demo(p).id,
            index=0,
        ),
    ),
    "PromoteTake": lambda p: (
        p,
        PromoteTake(beat_id=_acc(p).id, segment_id=_acc(p).takes[1].segment_id),
    ),
    "TrimItem": lambda p: (
        p,
        TrimItem(item_id=_intro(p).cut[0].id, source_in_us=900_000, source_out_us=6_000_000),
    ),
    "BladeItem": lambda p: (p, BladeItem(item_id=_acc(p).cut[1].id, at_us=20_000_000)),
    "SetItemEnabled": lambda p: (p, SetItemEnabled(item_id=_demo(p).cut[0].id, enabled=False)),
    "SetClipAudio": lambda p: (
        p,
        SetClipAudio(item_id=_demo(p).cut[0].id, audio=ClipAudio(mode="muted", gain_db=-6)),
    ),
    "SetTransition": lambda p: (
        p,
        SetTransition(
            transition=Transition(
                id=ids.new_id(ids.TRANSITION),
                after_item_id=_acc(p).cut[0].id,
                before_item_id=_acc(p).cut[1].id,
                type="dip_white",
            )
        ),
    ),
    "PutTransition": lambda p: (
        p,
        PutTransition(transition=p.transitions[1].model_copy(update={"duration_us": 1_000_000})),
    ),
    "RemoveTransition": lambda p: (p, RemoveTransition(transition_id=p.transitions[0].id)),
    "PutOverlay": lambda p: (
        p,
        PutOverlay(
            overlay=OverlayItem(
                id=ids.new_id(ids.OVERLAY),
                asset_id=p.assets[2].id,
                source_in_us=0,
                source_out_us=2_000_000,
                anchor=BeatAnchor(beat_id=_demo(p).id, offset_us=500_000),
            ),
            index=0,
        ),
    ),
    "RemoveOverlay": lambda p: (p, RemoveOverlay(overlay_id=p.overlays[0].id)),
    "PutConstraint": lambda p: (
        p,
        PutConstraint(
            constraint=GroupingConstraint(
                id=ids.new_id(ids.CONSTRAINT),
                type="must_link",
                a="seg_x",
                b="seg_y",
                created_at="2026-10-23T12:00:00Z",
            )
        ),
    ),
    "RemoveConstraint": lambda p: (p, RemoveConstraint(constraint_id=p.constraints[0].id)),
    "PutMarker": lambda p: (
        p,
        PutMarker(marker=p.markers[0].model_copy(update={"note": "edited", "color": None})),
    ),
    "RemoveMarker": lambda p: (p, RemoveMarker(marker_id=p.markers[1].id)),
    "PutTranscriptEdit": lambda p: (
        p,
        PutTranscriptEdit(
            edit=TranscriptEdit(
                id=ids.new_id(ids.TRANSCRIPT_EDIT),
                asset_id=p.assets[1].id,
                range=TimeRange(start_us=0, end_us=500_000),
                text="Bonjour",
            ),
            index=0,
        ),
    ),
    "RemoveTranscriptEdit": lambda p: (
        p,
        RemoveTranscriptEdit(edit_id=p.overrides.transcript_edits[0].id),
    ),
    "SetSegmentDismissed": lambda p: (
        p,
        SetSegmentDismissed(segment_id=p.overrides.dismissed_segment_ids[0], dismissed=False),
    ),
    "Batch": lambda p: (
        p,
        Batch(
            commands=[
                MoveBeat(beat_id=_demo(p).id, to_index=0),
                BladeItem(item_id=_intro(p).cut[0].id, at_us=3_000_000),
                PromoteTake(beat_id=_acc(p).id, segment_id=_acc(p).takes[1].segment_id),
                RemoveTransition(transition_id=p.transitions[2].id),
            ]
        ),
    ),
}


def test_every_command_type_has_a_sample() -> None:
    names = {c.model_fields["type"].default for c in COMMAND_TYPES}
    assert names == set(SAMPLES)


@pytest.mark.parametrize("name", sorted(SAMPLES))
def test_apply_then_inverse_restores_identical_project(project: Project, name: str) -> None:
    base, cmd = SAMPLES[name](project)
    before = base.dump()

    applied, inverse = cmd.apply(base)
    assert base.dump() == before, "apply must not mutate its input"
    assert applied.dump() != before, "sample command should change something"
    assert invariant_violations(applied) == []

    restored, redo = inverse.apply(applied)
    assert restored == base
    assert restored.dump() == before

    reapplied, _ = redo.apply(restored)
    assert reapplied.dump() == applied.dump()

    # Commands and inverses survive the wire format.
    for c in (cmd, inverse, redo):
        assert parse_command(c.dump()).dump() == c.dump()


def test_command_list_json_round_trip(project: Project) -> None:
    cmds = [SAMPLES[n](project)[1] for n in sorted(SAMPLES) if n != "RemoveAsset"]
    payload = command_list_adapter.dump_python(cmds, mode="json", by_alias=True)
    assert [c.dump() for c in command_list_adapter.validate_python(payload)] == payload


def test_blade_rules(project: Project) -> None:
    acc = _acc(project)
    item = acc.cut[1]  # has replaced audio, fade out, a marker at 20 s and transition after it
    trans_after = next(t for t in project.transitions if t.after_item_id == item.id)
    cmd = BladeItem(item_id=item.id, at_us=20_000_000)
    p, _ = cmd.apply(project)
    left, right = _acc(p).cut[1], _acc(p).cut[2]

    assert left.id == item.id and right.id == cmd.new_item_id
    assert (left.source_in_us, left.source_out_us) == (item.source_in_us, 20_000_000)
    assert (right.source_in_us, right.source_out_us) == (20_000_000, item.source_out_us)
    assert left.audio.fade_out_us == 0 and right.audio.fade_out_us == item.audio.fade_out_us
    assert right.audio.fade_in_us == 0
    assert item.audio.replacement is not None and right.audio.replacement is not None
    assert right.audio.replacement.source_in_us == (
        item.audio.replacement.source_in_us + 20_000_000 - item.source_in_us
    )
    moved = next(t for t in p.transitions if t.id == trans_after.id)
    assert moved.after_item_id == right.id
    assert p.is_transition_active(moved)
    marker = next(m for m in p.markers if m.id == project.markers[0].id)
    assert isinstance(marker.target, ItemMarkerTarget) and marker.target.item_id == right.id
    assert _acc(p).locked
    # Total main-line duration unchanged.
    total = sum(c.duration_us for _, c in project.main_line())
    assert sum(c.duration_us for _, c in p.main_line()) == total


@pytest.mark.parametrize("at", [18_000_000, 26_700_000, 10_000_000])
def test_blade_outside_item_is_rejected(project: Project, at: int) -> None:
    before = project.dump()
    with pytest.raises(CommandError):
        BladeItem(item_id=_acc(project).cut[1].id, at_us=at).apply(project)
    assert project.dump() == before


def test_promote_rules(project: Project) -> None:
    acc = _acc(project)
    p0, _ = SetClipAudio(
        item_id=acc.cut[0].id, audio=ClipAudio(gain_db=-6.0, fade_in_us=100_000)
    ).apply(project)
    p0 = p0.model_copy(update={"revision": project.revision})
    alt = acc.takes[1]
    cmd = PromoteTake(beat_id=acc.id, segment_id=alt.segment_id)
    p, _ = cmd.apply(p0)
    beat = _acc(p)

    assert [t.status for t in beat.takes] == ["alternate", "selected", "rejected"]
    assert len(beat.cut) == 1
    item = beat.cut[0]
    assert item.id == cmd.new_item_id
    assert item.asset_id == alt.asset_id and item.segment_id == alt.segment_id
    pad = project.settings.clip_padding
    assert item.source_in_us == alt.range.start_us - pad.before_us
    assert item.source_out_us == alt.range.end_us + pad.after_us
    assert item.audio.gain_db == -6.0 and item.audio.fade_in_us == 100_000
    assert beat.locked

    by_id = {t.id: t for t in p.transitions}
    d1, d2 = project.transitions[0], project.transitions[1]
    assert by_id[d1.id].before_item_id == item.id
    assert by_id[d2.id].after_item_id == item.id
    assert p.is_transition_active(by_id[d1.id]) and p.is_transition_active(by_id[d2.id])
    assert invariant_violations(p) == []


def test_promote_clamps_padding_to_media(project: Project) -> None:
    acc = _acc(project)
    rejected = acc.takes[2]  # starts at 0.3 s: padding before is clamped at 0
    p, _ = PromoteTake(beat_id=acc.id, segment_id=rejected.segment_id).apply(project)
    assert _acc(p).cut[0].source_in_us == 150_000
    demo = _demo(p)
    asset = p.asset(demo.takes[0].asset_id)
    assert asset is not None
    tail = TakeRef(
        segment_id="seg_tail",
        asset_id=asset.id,
        range=TimeRange(start_us=30_000_000, end_us=asset.probe.duration_us - 100_000),
    )
    p, _ = PutBeat(beat=demo.model_copy(update={"takes": [*demo.takes, tail]})).apply(p)
    p, _ = PromoteTake(beat_id=demo.id, segment_id="seg_tail").apply(p)
    assert _demo(p).cut[0].source_out_us == asset.probe.duration_us


def test_reorder_makes_transition_dormant_and_back(project: Project) -> None:
    d1, d2 = project.transitions[0], project.transitions[1]
    demo = _demo(project)
    p, inverse = MoveBeat(beat_id=demo.id, to_index=0).apply(project)
    assert [b.id for b in p.beats][0] == demo.id
    assert p.is_transition_active(d1)  # intro -> acc still adjacent
    assert not p.is_transition_active(d2)  # acc -> demo broken: dormant, not deleted
    assert d2 in p.transitions
    overlay = p.overlays[0]
    assert isinstance(overlay.anchor, BeatAnchor) and overlay.anchor.beat_id == _acc(p).id
    back, _ = inverse.apply(p)
    assert back.is_transition_active(d2)


def test_exclude_and_ripple_delete_make_transitions_dormant(project: Project) -> None:
    d1, d2 = project.transitions[0], project.transitions[1]
    p, _ = SetBeatIncluded(beat_id=_acc(project).id, included=False).apply(project)
    assert not p.is_transition_active(d1) and not p.is_transition_active(d2)
    p, _ = SetItemEnabled(item_id=_acc(project).cut[1].id, enabled=False).apply(project)
    assert p.is_transition_active(d1) and not p.is_transition_active(d2)
    assert len(p.main_line()) == len(project.main_line()) - 1


def test_set_transition_requires_adjacent_items(project: Project) -> None:
    t = Transition(
        id=ids.new_id(ids.TRANSITION),
        after_item_id=_intro(project).cut[0].id,
        before_item_id=_demo(project).cut[0].id,
    )
    with pytest.raises(CommandError):
        SetTransition(transition=t).apply(project)


def test_set_transition_replaces_the_one_on_the_same_cut(project: Project) -> None:
    old = project.transitions[0]
    new = Transition(
        id=ids.new_id(ids.TRANSITION),
        after_item_id=old.after_item_id,
        before_item_id=old.before_item_id,
        type="dip_black",
    )
    p, inverse = SetTransition(transition=new).apply(project)
    assert [t.id for t in p.transitions][0] == new.id and len(p.transitions) == 3
    assert inverse.apply(p)[0] == project


@pytest.mark.parametrize(
    "make",
    [
        lambda p: RemoveAsset(asset_id=p.assets[0].id),
        lambda p: RemoveBeat(beat_id=_acc(p).id),  # an overlay is anchored to it
        lambda p: TrimItem(item_id=_intro(p).cut[0].id, source_in_us=0, source_out_us=99_000_000),
        lambda p: SetTakeStatus(beat_id=_acc(p).id, segment_id="seg_nope", status="rejected"),
        lambda p: PromoteTake(
            beat_id=_acc(p).id,
            segment_id=_acc(p).takes[0].segment_id,
            new_item_id=_intro(p).cut[0].id,
        ),  # fmt: skip
        lambda p: MoveTake(segment_id="seg_nope", from_beat_id=_acc(p).id, to_beat_id=_demo(p).id),
        lambda p: PutSyncGroup(
            group=SyncGroup(id="sgp_other", members=[SyncMember(asset_id=p.assets[0].id)])
        ),
        lambda p: AddBeat(beat=_acc(p)),
        lambda p: UpdateBeat(beat_id=_acc(p).id, label=None),
        lambda p: RemoveMarker(marker_id="mrk_missing"),
    ],
)
def test_invalid_commands_raise_and_leave_input_untouched(
    project: Project, make: Callable[[Project], Command]
) -> None:
    before = project.dump()
    with pytest.raises(CommandError):
        make(project).apply(project)
    assert project.dump() == before


def test_update_beat_only_touches_given_fields(project: Project) -> None:
    demo = _demo(project)
    p, _ = UpdateBeat(beat_id=demo.id, summary="Nouveau résumé").apply(project)
    assert _demo(p).label == demo.label and _demo(p).summary == "Nouveau résumé"
    assert _demo(p).locked
    p, _ = UpdateBeat(beat_id=demo.id, locked=False, role="teaser").apply(project)
    assert not _demo(p).locked and _demo(p).role == "teaser"


def test_move_take_demotes_selected(project: Project) -> None:
    acc, demo = _acc(project), _demo(project)
    seg = acc.takes[0].segment_id
    p, _ = MoveTake(segment_id=seg, from_beat_id=acc.id, to_beat_id=demo.id).apply(project)
    moved = _demo(p).take(seg)
    assert moved is not None and moved.status == "alternate"
    assert _acc(p).take(seg) is None
    assert _acc(p).locked and _demo(p).locked


def test_add_take_via_put_beat(project: Project) -> None:
    demo = _demo(project)
    take = TakeRef(
        segment_id="seg_extra",
        asset_id=project.assets[0].id,
        range=TimeRange(start_us=1, end_us=2),
    )
    beat = demo.model_copy(update={"takes": [*demo.takes, take]})
    p, _ = PutBeat(beat=beat).apply(project)
    assert _demo(p).take("seg_extra") is not None


def test_overlay_with_project_anchor(project: Project) -> None:
    o = OverlayItem(
        id=ids.new_id(ids.OVERLAY),
        asset_id=project.assets[2].id,
        source_in_us=0,
        source_out_us=1_000_000,
        anchor=ProjectAnchor(time_us=2_000_000),
    )
    p, _ = PutOverlay(overlay=o).apply(project)
    assert p.overlays[-1].anchor == ProjectAnchor(time_us=2_000_000)


def test_apply_batch_bumps_revision_and_undo(project: Project) -> None:
    acc, demo = _acc(project), _demo(project)
    cmds: list[Command] = [
        MoveBeat(beat_id=demo.id, to_index=0),
        BladeItem(item_id=acc.cut[0].id, at_us=15_000_000),
        SetItemEnabled(item_id=acc.cut[1].id, enabled=False),
    ]
    p, inverses = apply_batch(project, cmds)
    assert p.revision == project.revision + 1
    undone, redo = apply_batch(p, inverses)
    assert undone.revision == project.revision + 2
    assert undone.model_copy(update={"revision": project.revision}) == project
    redone, _ = apply_batch(undone, redo)
    assert redone.model_copy(update={"revision": p.revision}).dump() == p.dump()


def test_apply_batch_is_all_or_nothing(project: Project) -> None:
    before = project.dump()
    with pytest.raises(CommandError):
        apply_batch(
            project,
            [RenameProject(name="x"), RemoveTransition(transition_id="tr_missing")],
        )
    assert project.dump() == before


def _random_command(p: Project, data: st.DataObject) -> Command | None:
    kind = data.draw(st.sampled_from(["trim", "blade", "move", "enable", "promote", "include"]))
    items = [(b, c) for b in p.beats for c in b.cut]
    if kind == "move":
        beat = data.draw(st.sampled_from(p.beats))
        return MoveBeat(beat_id=beat.id, to_index=data.draw(st.integers(0, len(p.beats))))
    if kind == "include":
        beat = data.draw(st.sampled_from(p.beats))
        return SetBeatIncluded(beat_id=beat.id, included=data.draw(st.booleans()))
    if kind == "promote":
        beat = data.draw(st.sampled_from([b for b in p.beats if b.takes]))
        take = data.draw(st.sampled_from(beat.takes))
        return PromoteTake(beat_id=beat.id, segment_id=take.segment_id)
    _, item = data.draw(st.sampled_from(items))
    if kind == "enable":
        return SetItemEnabled(item_id=item.id, enabled=data.draw(st.booleans()))
    if item.duration_us < 3:
        return None
    if kind == "blade":
        at = data.draw(st.integers(item.source_in_us + 1, item.source_out_us - 1))
        return BladeItem(item_id=item.id, at_us=at)
    new_in = data.draw(st.integers(max(0, item.source_in_us - 100_000), item.source_out_us - 2))
    new_out = data.draw(st.integers(new_in + 1, item.source_out_us))
    return TrimItem(item_id=item.id, source_in_us=new_in, source_out_us=new_out)


@settings(max_examples=40, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(data=st.data())
def test_random_edit_sequences_undo_to_the_original(data: st.DataObject) -> None:
    original = Project.model_validate(load_fixture_dict())
    p = original
    undo_stack: list[list[Command]] = []
    for _ in range(data.draw(st.integers(1, 12))):
        cmd = _random_command(p, data)
        if cmd is None:
            continue
        p, inverses = apply_batch(p, [cmd])
        assert invariant_violations(p) == []
        undo_stack.append(inverses)
    while undo_stack:
        p, _ = apply_batch(p, undo_stack.pop())
    assert p.model_copy(update={"revision": original.revision}) == original
