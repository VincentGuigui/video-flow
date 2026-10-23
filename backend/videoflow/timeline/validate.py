"""Structural checks on a :class:`ResolvedTimeline`.

:func:`invariant_violations` lists broken invariants (empty when the timeline is
consistent); consumers (OTIO compiler, render) can assert on it before compiling.
:func:`overlap_warnings` reports overlays that cover each other on the same track.
"""

from videoflow.timeline.handles import split
from videoflow.timeline.resolved import (
    ResolvedClip,
    ResolvedTimeline,
    ResolvedTransition,
    TimelineWarning,
)


def _check_main_line(tl: ResolvedTimeline, problems: list[str]) -> list[ResolvedClip]:
    v1 = tl.track("V1")
    a1 = tl.track("A1")
    video = v1.clips if v1 else []
    position = 0
    for clip in video:
        if clip.timeline_start != position:
            problems.append(
                f"V1 clip {clip.item_id} starts at {clip.timeline_start}, not {position}"
            )
        if clip.duration <= 0:
            problems.append(f"V1 clip {clip.item_id} has no frames")
        position = clip.timeline_end
    if position != tl.duration:
        problems.append(f"timeline duration {tl.duration} != sum of V1 clips {position}")
    audio = a1.clips if a1 else []
    if [(c.item_id, c.timeline_start, c.duration) for c in audio] != [
        (c.item_id, c.timeline_start, c.duration) for c in video
    ]:
        problems.append("A1 does not mirror V1 timing")
    else:
        for v, a in zip(video, audio, strict=True):
            if (v.handle_before, v.handle_after) != (a.handle_before, a.handle_after):
                problems.append(f"A1 handles of {v.item_id} differ from V1")
    return video


def _check_transition(
    tr: ResolvedTransition, index: dict[str, int], video: list[ResolvedClip], problems: list[str]
) -> None:
    i = index.get(tr.after_item_id)
    j = index.get(tr.before_item_id)
    if i is None or j != i + 1:
        problems.append(f"active transition {tr.transition_id} is not on adjacent clips")
        return
    left, right = video[i], video[j]
    if tr.cut_frame != right.timeline_start:
        problems.append(f"transition {tr.transition_id} cut frame is not at its right clip")
    if tr.left_frames + tr.right_frames != tr.duration or tr.duration <= 0:
        problems.append(f"transition {tr.transition_id} split does not add up")
    alignment = str(tr.alignment)
    if alignment in ("center", "start", "end") and split(tr.duration, alignment) != (  # type: ignore[arg-type]
        tr.left_frames,
        tr.right_frames,
    ):
        problems.append(f"transition {tr.transition_id} split does not match {alignment}")
    if left.handle_after != tr.right_frames or right.handle_before != tr.left_frames:
        problems.append(f"transition {tr.transition_id} handles do not match its clips")
    if tr.audio_duration > tr.duration:
        problems.append(f"transition {tr.transition_id} audio is longer than the video")


def invariant_violations(tl: ResolvedTimeline) -> list[str]:
    """Human-readable list of broken resolved-timeline invariants."""
    problems: list[str] = []
    video = _check_main_line(tl, problems)
    index = {c.item_id: i for i, c in enumerate(video)}

    with_transition: set[str] = set()
    for tr in tl.transitions:
        if tr.state != "active":
            problems.append(f"transition {tr.transition_id} in the active list is {tr.state}")
        _check_transition(tr, index, video, problems)
        with_transition.update((tr.after_item_id, tr.before_item_id))
    cuts = [t.cut_frame or 0 for t in tl.transitions]
    if cuts != sorted(cuts):
        problems.append("active transitions are not in timeline order")
    for tr in tl.dormant_transitions:
        if tr.state != "dormant" or tr.duration or tr.cut_frame is not None:
            problems.append(f"dormant transition {tr.transition_id} carries active data")

    for clip in video:
        if (clip.handle_before or clip.handle_after) and clip.item_id not in with_transition:
            problems.append(f"clip {clip.item_id} has handles without a transition")
    # Visible frames of each clip taken by its incoming (after the cut) and outgoing
    # (before the cut) transitions must not overlap.
    taken = [0] * len(video)
    for tr in tl.transitions:
        i = index.get(tr.after_item_id)
        if i is None or i + 1 >= len(video):
            continue
        taken[i] += tr.left_frames
        taken[i + 1] += tr.right_frames
    for clip, frames_taken in zip(video, taken, strict=True):
        if frames_taken > clip.duration:
            problems.append(f"transitions overlap on clip {clip.item_id}")

    rendered = sum(c.duration + c.handle_before + c.handle_after for c in video)
    if rendered - sum(t.duration for t in tl.transitions) != tl.duration:
        problems.append("sum of rendered clips minus transitions != timeline duration")

    for track in tl.tracks:
        if track.id in ("V1", "A1"):
            continue
        for clip in track.clips:
            if clip.timeline_start < 0 or clip.timeline_end > tl.duration or clip.duration <= 0:
                problems.append(f"overlay {clip.item_id} is outside the main line")
    return problems


def overlap_warnings(tl: ResolvedTimeline) -> list[TimelineWarning]:
    """Overlays that overlap an earlier overlay on the same track (the later one wins)."""
    warnings: list[TimelineWarning] = []
    for track in tl.tracks:
        if track.id in ("V1", "A1"):
            continue
        end = -1
        previous: str | None = None
        for clip in sorted(track.clips, key=lambda c: (c.timeline_start, c.item_id)):
            if previous is not None and clip.timeline_start < end:
                warnings.append(
                    TimelineWarning(
                        code="overlay_overlap",
                        message=f"overlay overlaps {previous} on {track.id}",
                        item_id=clip.item_id,
                    )
                )
            if clip.timeline_end > end:
                end, previous = clip.timeline_end, clip.item_id
    return warnings
