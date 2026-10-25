"""Compile resolved frame positions to OTIO; source ranges exclude transition handles."""

from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

import opentimelineio as otio

from videoflow.core.time import frames
from videoflow.project.models import Project
from videoflow.timeline.handles import split
from videoflow.timeline.resolved import ResolvedClip, ResolvedTimeline, ResolvedTransition


def media_url(path: str) -> str:
    """Portable file URLs, including Windows projects exported on Linux."""
    if PureWindowsPath(path).is_absolute():
        return PureWindowsPath(path).as_uri()
    if path.startswith("/"):
        return PurePosixPath(path).as_uri()
    return Path(path).absolute().as_uri()


def compile_timeline(
    resolved: ResolvedTimeline, project: Project, *, include_alternates: bool = False
) -> Any:
    """Build a fresh OTIO object without modifying either input.

    Gain, fades, fit and freeze handles are metadata; finishing tools may ignore them.
    Overlapping overlays occupy separate tracks so no clip's timing is lost.
    """
    rate = float(resolved.rate)

    def rt(value: int) -> Any:
        return otio.opentime.RationalTime(value, rate)

    def time_range(start: int, duration: int) -> Any:
        return otio.opentime.TimeRange(rt(start), rt(duration))

    assets = {a.id: a for a in project.assets}
    timeline = otio.schema.Timeline(name=project.name, global_start_time=rt(0))
    timeline.metadata["videoflow"] = {
        "projectId": resolved.project_id,
        "revision": resolved.revision,
        "rate": resolved.rate.dump(),
        "width": resolved.width,
        "height": resolved.height,
        "sampleRate": resolved.sample_rate,
        "warnings": [w.dump() for w in resolved.warnings],
        "dormantTransitions": [t.dump() for t in resolved.dormant_transitions],
        "limitations": ["Clip gain, fades, fit and freeze handles are metadata only."],
    }

    def child(clip: ResolvedClip, kind: str) -> Any:
        asset = assets.get(clip.asset_id)
        silent = kind == "audio" and (
            (clip.audio is not None and clip.audio.mode == "muted")
            or (asset is not None and not asset.probe.has_audio)
        )
        if silent:
            result = otio.schema.Gap(source_range=time_range(0, clip.duration))
        else:
            reference = (
                otio.schema.ExternalReference(
                    target_url=media_url(asset.path),
                    available_range=time_range(0, frames(asset.probe.duration_us, resolved.rate)),
                )
                if asset is not None
                else otio.schema.MissingReference()
            )
            result = otio.schema.Clip(
                name=Path(asset.path.replace("\\", "/")).name if asset else clip.asset_id,
                media_reference=reference,
                source_range=time_range(clip.source_in_frame, clip.duration),
            )
        result.metadata["videoflow"] = clip.dump()
        return result

    def transition(tr: ResolvedTransition, kind: str) -> Any | None:
        before, after = tr.left_frames, tr.right_frames
        if kind == "audio":
            if tr.audio == "cut" or tr.audio_duration == 0:
                return None
            before, after = split(tr.audio_duration, str(tr.alignment))  # type: ignore[arg-type]
        result = otio.schema.Transition(
            name=tr.type,
            transition_type=(
                otio.schema.TransitionTypes.SMPTE_Dissolve
                if tr.type == "dissolve" or kind == "audio"
                else otio.schema.TransitionTypes.Custom
            ),
            in_offset=rt(before),
            out_offset=rt(after),
        )
        result.metadata["videoflow"] = {"transition": tr.dump()}
        return result

    transitions = {t.after_item_id: t for t in resolved.transitions}
    # OTIO stack order is bottom to top: audio, main picture, then overlays.
    for source in sorted(resolved.tracks, key=lambda t: (t.kind == "video", t.id != "V1")):
        lanes: list[list[ResolvedClip]] = []
        for clip in sorted(source.clips, key=lambda c: (c.timeline_start, c.item_id)):
            lane = next((v for v in lanes if v[-1].timeline_end <= clip.timeline_start), None)
            if lane is None:
                lane = []
                lanes.append(lane)
            lane.append(clip)
        for lane_index, clips in enumerate(lanes):
            name = str(source.id) + (f".{lane_index + 1}" if lane_index else "")
            track = otio.schema.Track(name=name, kind=source.kind.capitalize())
            track.metadata["videoflow"] = {"trackId": str(source.id)}
            cursor = 0
            for clip in clips:
                if clip.timeline_start > cursor:
                    track.append(
                        otio.schema.Gap(source_range=time_range(0, clip.timeline_start - cursor))
                    )
                track.append(child(clip, source.kind))
                if source.id in ("V1", "A1") and clip.item_id in transitions:
                    item = transition(transitions[clip.item_id], source.kind)
                    if item is not None:
                        track.append(item)
                cursor = clip.timeline_end
            if cursor < resolved.duration:
                track.append(
                    otio.schema.Gap(source_range=time_range(0, resolved.duration - cursor))
                )
            timeline.tracks.append(track)

    if include_alternates:
        for beat in project.beats:
            span = next((s for s in resolved.beats if s.beat_id == beat.id), None)
            if span is None:
                continue
            used = {c.segment_id for c in beat.cut if c.enabled}
            for take in beat.takes:
                if take.segment_id in used or take.status == "rejected":
                    continue
                track = otio.schema.Track(name=f"ALT {beat.label}: {take.segment_id}", kind="Video")
                track.enabled = False
                track.source_range = time_range(0, resolved.duration)
                if span.start:
                    track.append(otio.schema.Gap(source_range=time_range(0, span.start)))
                start = frames(take.range.start_us, resolved.rate)
                duration = frames(take.range.end_us, resolved.rate) - start
                track.append(
                    child(
                        ResolvedClip(
                            item_id=take.segment_id,
                            track="V2",
                            asset_id=take.asset_id,
                            beat_id=beat.id,
                            segment_id=take.segment_id,
                            take_status=str(take.status),
                            timeline_start=span.start,
                            duration=duration,
                            source_in_us=take.range.start_us,
                            source_out_us=take.range.end_us,
                            source_in_frame=start,
                        ),
                        "video",
                    )
                )
                timeline.tracks.append(track)
    for marker in resolved.markers:
        timeline.tracks.markers.append(
            otio.schema.Marker(
                name=marker.note,
                marked_range=time_range(marker.frame, 0),
                metadata={"videoflow": marker.dump()},
            )
        )
    return timeline


def serialize(timeline: Any) -> str:
    return str(otio.adapters.write_to_string(timeline, adapter_name="otio_json"))
