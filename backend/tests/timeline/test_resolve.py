from fractions import Fraction

from hypothesis import given, settings
from hypothesis import strategies as st

from tests.timeline.builders import (
    ProjectBuilder,
    S,
    beat_overlay,
    clip,
    project_overlay,
    transition,
)
from tests.timeline.test_golden import alignments, full_fixture, ntsc_ripple
from videoflow.core.time import Rational, clip_frames
from videoflow.project.commands import BladeItem, MoveBeat, SetBeatIncluded, SetItemEnabled
from videoflow.project.models import Project
from videoflow.timeline.resolve import resolve
from videoflow.timeline.resolved import ResolvedClip, ResolvedTimeline
from videoflow.timeline.validate import invariant_violations


def v1(tl: ResolvedTimeline) -> list[ResolvedClip]:
    track = tl.track("V1")
    assert track is not None
    return track.clips


def codes(tl: ResolvedTimeline) -> list[str]:
    return [w.code for w in tl.warnings]


def three_clips() -> Project:
    b = ProjectBuilder()
    b.asset("ast_a", 60 * S)
    b.beat("beat_1", clip("clip_a", "ast_a", 10 * S, 14 * S))
    b.beat(
        "beat_2", clip("clip_b", "ast_a", 20 * S, 22 * S), clip("clip_b2", "ast_a", 25 * S, 26 * S)
    )
    b.beat("beat_3", clip("clip_c", "ast_a", 30 * S, 33 * S))
    b.transitions += [
        transition("tr_ab", "clip_a", "clip_b"),
        transition("tr_bc", "clip_b2", "clip_c"),
    ]
    return b.build()


# --------------------------------------------------------------------------- main line


def test_positions_are_cumulative_frame_counts() -> None:
    tl = resolve(ntsc_ripple())
    position = 0
    for c in v1(tl):
        assert c.timeline_start == position
        assert c.duration == clip_frames(c.source_in_us, c.source_out_us, tl.rate)
        position += c.duration
    assert tl.duration == position


def test_total_frames_identity_with_handles() -> None:
    for project in (full_fixture(), alignments(), ntsc_ripple(), three_clips()):
        tl = resolve(project)
        clips = v1(tl)
        visible = sum(c.duration for c in clips)
        rendered = sum(c.duration + c.handle_before + c.handle_after for c in clips)
        assert tl.duration == visible == rendered - sum(t.duration for t in tl.transitions)
        assert invariant_violations(tl) == []


def test_disabled_item_ripples() -> None:
    project = three_clips()
    before = resolve(project)
    edited, _ = SetItemEnabled(item_id="clip_b2", enabled=False).apply(project)
    after = resolve(edited)
    removed = next(c for c in v1(before) if c.item_id == "clip_b2").duration
    assert [c.item_id for c in v1(after)] == ["clip_a", "clip_b", "clip_c"]
    assert after.duration == before.duration - removed
    assert v1(after)[2].timeline_start == v1(after)[1].timeline_end
    # clip_c was after clip_b2: tr_bc is dormant now
    assert [t.transition_id for t in after.dormant_transitions] == ["tr_bc"]
    assert "dormant_transition" in codes(after)
    assert invariant_violations(after) == []


def test_excluded_beat_ripples_and_makes_transition_dormant() -> None:
    project = three_clips()
    edited, _ = SetBeatIncluded(beat_id="beat_2", included=False).apply(project)
    tl = resolve(edited)
    assert [c.item_id for c in v1(tl)] == ["clip_a", "clip_c"]
    assert tl.duration == 120 + 90
    assert tl.transitions == []
    assert {t.transition_id for t in tl.dormant_transitions} == {"tr_ab", "tr_bc"}
    assert all(t.duration == 0 and t.cut_frame is None for t in tl.dormant_transitions)
    assert all(c.handle_before == c.handle_after == 0 for c in v1(tl))
    assert [b.beat_id for b in tl.beats] == ["beat_1", "beat_3"]


def test_reorder_makes_transition_dormant_and_back() -> None:
    project = three_clips()
    moved, inverse = MoveBeat(beat_id="beat_3", to_index=0).apply(project)
    tl = resolve(moved)
    assert [c.item_id for c in v1(tl)] == ["clip_c", "clip_a", "clip_b", "clip_b2"]
    assert [t.transition_id for t in tl.transitions] == ["tr_ab"]
    assert [t.transition_id for t in tl.dormant_transitions] == ["tr_bc"]
    warning = next(w for w in tl.warnings if w.code == "dormant_transition")
    assert warning.transition_id == "tr_bc"
    restored, _ = inverse.apply(moved)
    assert resolve(restored) == resolve(project)


def test_blade_keeps_transition_on_right_part() -> None:
    project = three_clips()
    edited, _ = BladeItem(item_id="clip_b2", at_us=25_500_000, new_item_id="clip_b3").apply(project)
    tl = resolve(edited)
    tr = next(t for t in tl.transitions if t.transition_id == "tr_bc")
    assert tr.after_item_id == "clip_b3"
    assert tl.duration == resolve(project).duration


def test_audio_replacement_on_a1() -> None:
    tl = resolve(full_fixture())
    a1 = tl.track("A1")
    assert a1 is not None
    replaced = next(c for c in a1.clips if c.item_id == "clip_01K884QRM0000000000000009F")
    assert replaced.asset_id == "ast_01K884QRM00000000000000004"
    assert replaced.source_in_us == 21_217_000
    assert [(c.timeline_start, c.duration) for c in a1.clips] == [
        (c.timeline_start, c.duration) for c in v1(tl)
    ]


def test_empty_clip_is_skipped() -> None:
    b = ProjectBuilder()
    b.asset("ast_a", 60 * S)
    b.beat(
        "beat_1", clip("clip_a", "ast_a", S, 2 * S), clip("clip_tiny", "ast_a", 3 * S, 3 * S + 10)
    )
    tl = resolve(b.build())
    assert [c.item_id for c in v1(tl)] == ["clip_a"]
    assert codes(tl) == ["empty_clip"]


def test_missing_asset_warns_once() -> None:
    b = ProjectBuilder()
    b.beat("beat_1", clip("clip_a", "ast_gone", S, 2 * S), clip("clip_b", "ast_gone", 3 * S, 4 * S))
    tl = resolve(b.build())
    assert codes(tl) == ["missing_asset"]
    assert v1(tl)[0].available_after is None


# --------------------------------------------------------------------------- transitions


def test_alignment_handles() -> None:
    tl = resolve(alignments())
    by_id = {t.transition_id: t for t in tl.transitions}
    clips = {c.item_id: c for c in v1(tl)}
    center, start, end = by_id["tr_center"], by_id["tr_start"], by_id["tr_end"]
    # center, odd 15 frames: 7 before the cut (right head), 8 after (left tail)
    assert (center.duration, center.left_frames, center.right_frames) == (15, 7, 8)
    assert (clips["clip_a"].handle_after, clips["clip_b"].handle_before) == (8, 7)
    assert center.start_frame == 120 - 7
    # start: left clip tail T, transition entirely after the cut
    assert (start.left_frames, start.right_frames) == (0, 12)
    assert (clips["clip_b"].handle_after, clips["clip_c"].handle_before) == (12, 0)
    assert start.start_frame == start.cut_frame
    # end: right clip head T, transition entirely before the cut
    assert (end.left_frames, end.right_frames) == (12, 0)
    assert (clips["clip_c"].handle_after, clips["clip_d"].handle_before) == (0, 12)
    assert end.start_frame == end.cut_frame - 12  # type: ignore[operator]
    assert tl.warnings == []


def test_transition_clamped_to_visible_frames() -> None:
    b = ProjectBuilder()
    b.asset("ast_a", 60 * S)
    b.beat("beat_1", clip("clip_a", "ast_a", 10 * S, 11 * S))  # 30 frames
    b.beat("beat_2", clip("clip_b", "ast_a", 20 * S, 20_400_000))  # 12 frames
    b.beat("beat_3", clip("clip_c", "ast_a", 30 * S, 31 * S))
    b.transitions += [
        transition("tr_ab", "clip_a", "clip_b", 2 * S, "start"),  # wants 60, fits 12
        transition("tr_bc", "clip_b", "clip_c", 1 * S, "end"),  # nothing left in clip_b
    ]
    tl = resolve(b.build())
    assert [(t.transition_id, t.duration) for t in tl.transitions] == [("tr_ab", 12)]
    assert [t.transition_id for t in tl.dormant_transitions] == ["tr_bc"]
    assert codes(tl) == ["transition_clamped", "transition_too_long"]
    assert invariant_violations(tl) == []


def test_insufficient_handles_keeps_transition_with_freeze() -> None:
    b = ProjectBuilder()
    b.asset("ast_a", 10 * S)
    b.beat("beat_1", clip("clip_a", "ast_a", 5 * S, 9_900_000))  # 3 tail frames available
    b.beat("beat_2", clip("clip_b", "ast_a", 0, 2 * S))  # no head media
    b.transitions.append(transition("tr", "clip_a", "clip_b", 1 * S))
    tl = resolve(b.build())
    a, bb = v1(tl)
    assert tl.transitions[0].duration == 30
    assert (a.handle_after, a.available_after, a.freeze_after) == (15, 3, 12)
    assert (bb.handle_before, bb.available_before, bb.freeze_before) == (15, 0, 15)
    warning = next(w for w in tl.warnings if w.code == "insufficient_handles")
    assert warning.transition_id == "tr"
    assert "start <= 3" in warning.message


def test_cut_and_zero_transitions_are_hard_cuts() -> None:
    project = three_clips()
    project.transitions[0].type = "cut"
    project.transitions[1].duration_us = 10_000  # < half a frame at 30 fps
    tl = resolve(project)
    assert tl.transitions == [] and tl.dormant_transitions == [] and tl.warnings == []


def test_unknown_values_warn() -> None:
    project = three_clips()
    data = project.dump()
    data["transitions"][0]["type"] = "hologram"
    data["transitions"][0]["alignment"] = "middle"
    tl = resolve(Project.model_validate(data))
    assert tl.transitions[0].type == "hologram"
    assert tl.transitions[0].alignment == "center"
    assert codes(tl)[:2] == ["unknown_transition_type", "unknown_alignment"]


def test_transition_audio_modes() -> None:
    tl = resolve(full_fixture())
    by_id = {t.transition_id: t for t in tl.transitions}
    assert (
        by_id["tr_01K884QRM000000000000000CH"].audio,
        by_id["tr_01K884QRM000000000000000CH"].audio_duration,
    ) == ("follow", 15)
    crossfade = by_id["tr_01K884QRM000000000000000CJ"]
    assert (crossfade.audio, crossfade.audio_duration) == ("crossfade", 12)


# --------------------------------------------------------------------------- overlays


def overlay_project() -> Project:
    b = ProjectBuilder()
    b.asset("ast_a", 60 * S).asset("ast_broll", 20 * S)
    b.beat("beat_1", clip("clip_a", "ast_a", 0, 4 * S))  # frames 0-120
    b.beat("beat_2", clip("clip_b", "ast_a", 10 * S, 14 * S))  # frames 120-240
    b.overlays.append(beat_overlay("ovl_1", "ast_broll", "beat_2", S, 2 * S))
    return b.build()


def test_overlay_follows_its_beat() -> None:
    project = overlay_project()
    tl = resolve(project)
    v2 = tl.track("V2")
    assert v2 is not None and (v2.clips[0].timeline_start, v2.clips[0].duration) == (150, 60)
    moved, _ = MoveBeat(beat_id="beat_2", to_index=0).apply(project)
    v2 = resolve(moved).track("V2")
    assert v2 is not None and v2.clips[0].timeline_start == 30
    trimmed = project.model_copy(deep=True)
    trimmed.beats[0].cut[0].source_out_us = 2 * S  # beat_1 shortened by 60 frames
    v2 = resolve(trimmed).track("V2")
    assert v2 is not None and v2.clips[0].timeline_start == 90


def test_overlay_clamped_to_main_line() -> None:
    project = overlay_project()
    project.overlays[0].anchor.offset_us = 3 * S  # type: ignore[union-attr]
    tl = resolve(project)
    v2 = tl.track("V2")
    assert v2 is not None
    ovl = v2.clips[0]
    assert (ovl.timeline_start, ovl.duration, ovl.clamped) == (210, 30, True)
    assert ovl.source_out_us == 2 * S
    assert clip_frames(ovl.source_in_us, ovl.source_out_us, tl.rate) == ovl.duration
    assert codes(tl) == ["overlay_clamped"]
    assert invariant_violations(tl) == []

    project.overlays[0].anchor.offset_us = -10 * S  # type: ignore[union-attr]
    ovl = resolve(project).track("V2").clips[0]  # type: ignore[union-attr]
    assert (ovl.timeline_start, ovl.duration, ovl.clamped) == (0, 60, True)


def test_overlay_dropped_with_excluded_beat_or_out_of_range() -> None:
    project = overlay_project()
    project.overlays.append(project_overlay("ovl_far", "ast_broll", 100 * S, S))
    edited, _ = SetBeatIncluded(beat_id="beat_2", included=False).apply(project)
    tl = resolve(edited)
    v2 = tl.track("V2")
    assert v2 is not None and v2.clips == []
    assert [(w.code, w.item_id) for w in tl.warnings] == [
        ("overlay_dropped", "ovl_1"),
        ("overlay_dropped", "ovl_far"),
    ]


def test_overlay_overlap_warns() -> None:
    project = overlay_project()
    project.overlays.append(project_overlay("ovl_2", "ast_broll", 5 * S, 2 * S))
    tl = resolve(project)
    assert ("overlay_overlap", "ovl_2") in [(w.code, w.item_id) for w in tl.warnings]


def test_markers() -> None:
    tl = resolve(full_fixture())
    frames = {(m.marker_id[-1], m.item_id and m.item_id[-3:]): m.frame for m in tl.markers}
    # item marker at source 20 s in clip 9F (source 18 s, timeline 354): 354 + 60
    assert frames[("1", "09F")] == 354 + 60
    assert frames[("3", None)] == 0


# --------------------------------------------------------------------------- properties


@st.composite
def random_projects(draw: st.DrawFn) -> Project:
    rate = draw(
        st.sampled_from([Rational.of(25), Rational.of(30000, 1001), Rational.of(24000, 1001)])
    )
    b = ProjectBuilder(rate=rate)
    b.asset("ast_a", 3600 * S)
    n = draw(st.integers(min_value=1, max_value=25))
    ids: list[str] = []
    for i in range(n):
        start = draw(st.integers(min_value=0, max_value=3000 * S))
        length = draw(st.integers(min_value=1, max_value=8 * S))
        item = clip(f"clip_{i}", "ast_a", start, start + length)
        item.enabled = draw(st.booleans()) or i == 0
        b.beat(f"beat_{i}", item, included=draw(st.integers(0, 9)) > 0)
        ids.append(item.id)
    for i in range(n - 1):
        if draw(st.booleans()):
            b.transitions.append(
                transition(
                    f"tr_{i}",
                    ids[i],
                    ids[i + 1],
                    draw(st.integers(min_value=0, max_value=3 * S)),
                    draw(st.sampled_from(["center", "start", "end"])),
                )
            )
    if draw(st.booleans()):
        b.beats.reverse()
    return b.build()


@settings(max_examples=150, deadline=None)
@given(random_projects())
def test_random_projects_are_consistent(project: Project) -> None:
    tl = resolve(project)
    assert invariant_violations(tl) == []
    assert tl.duration == sum(
        clip_frames(c.source_in_us, c.source_out_us, tl.rate) for _, c in project.main_line()
    )
    # the frame count matches the exact rational duration within one frame per clip
    exact = sum(Fraction(c.duration_us, S) for _, c in project.main_line()) * tl.rate.fraction
    assert abs(tl.duration - exact) <= max(1, len(project.main_line()))
    assert resolve(project) == tl


def test_revision_only_changes_revision() -> None:
    project = three_clips()
    bumped = project.model_copy(update={"revision": 99})
    a, b = resolve(project).dump(), resolve(bumped).dump()
    assert a.pop("revision") != b.pop("revision")
    assert a == b
