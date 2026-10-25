"""Resolver: ``project.json`` decisions -> :class:`ResolvedTimeline` (integer frames).

Pure and deterministic; the OTIO compiler and the FFmpeg render both consume its output.

Rules
=====

* **Main line (V1 + A1)**: enabled cut items of included beats, in story order. Excluded
  beats and disabled items are simply absent, so later clips ripple left. A clip covers
  ``frames(out) - frames(in)`` frames and starts at the sum of the previous counts; a clip
  that quantises to 0 frames is dropped (``empty_clip``).
* **A1** mirrors V1 timing (audio follows the video frame count). Its asset and source
  range come from the audio replacement when ``audio.mode == "replaced"``.
* **Transitions** are active when their two items are adjacent on the resolved main line
  and their duration is at least one frame (type ``cut`` is a plain hard cut and emits
  nothing). Otherwise they are dormant: hard cut + ``dormant_transition`` warning.
  ``before`` / ``after`` cut frames follow :mod:`videoflow.timeline.handles`. A transition
  must fit inside the visible frames of its clips without overlapping the previous
  transition: it is shortened (``transition_clamped``) or, if nothing fits, made dormant
  (``transition_too_long``). A zero-frame transition is a hard cut too. Missing source
  media for a handle is not an error: the transition is kept, the render freezes a frame
  and ``insufficient_handles`` lists the alternatives that would fit (TR-06).
* **Overlays (V2)**: a beat anchor starts at the beat's visible start plus ``offset``,
  a project anchor at an absolute frame. Overlays are clamped to ``[0, duration)`` of the
  main line (``overlay_clamped``) and dropped when their beat is not on the main line or
  nothing remains (``overlay_dropped``). Disabled overlays are skipped.
* **Markers**: timeline markers at their frame; item markers where the item's source
  time is visible; asset markers at every visible occurrence of that source time.
"""

from collections.abc import Iterable

from videoflow.core.base import is_unknown
from videoflow.core.time import Micros, Rational, clip_frames, duration_frames, frame_to_us, frames
from videoflow.project.models import (
    Asset,
    AssetMarkerTarget,
    Beat,
    BeatAnchor,
    ClipItem,
    CrossfadeAudio,
    FitRect,
    ItemMarkerTarget,
    OverlayItem,
    Project,
    TimelineMarkerTarget,
    Transition,
)
from videoflow.timeline import handles
from videoflow.timeline.resolved import (
    BeatSpan,
    ResolvedAudio,
    ResolvedClip,
    ResolvedFit,
    ResolvedFitRect,
    ResolvedMarker,
    ResolvedTimeline,
    ResolvedTrack,
    ResolvedTransition,
    TimelineWarning,
)
from videoflow.timeline.validate import overlap_warnings


class _Context:
    def __init__(self, project: Project) -> None:
        self.project = project
        self.rate: Rational = project.settings.frame_rate
        self.assets: dict[str, Asset] = {a.id: a for a in project.assets}
        self.warnings: list[TimelineWarning] = []
        self._missing_reported: set[str] = set()

    def warn(self, code: str, message: str, **refs: str | None) -> None:
        self.warnings.append(TimelineWarning(code=code, message=message, **refs))

    def asset_duration(self, asset_id: str, item_id: str) -> Micros | None:
        asset = self.assets.get(asset_id)
        if asset is None:
            if asset_id not in self._missing_reported:
                self._missing_reported.add(asset_id)
                self.warn(
                    "missing_asset", f"asset {asset_id} is not in the project", item_id=item_id
                )
            return None
        return asset.probe.duration_us


# --------------------------------------------------------------------------- main line


def _audio(ctx: _Context, item: ClipItem, duration: int) -> ResolvedAudio:
    mode = item.audio.mode
    asset_id: str | None = item.asset_id
    source_in: Micros | None = item.source_in_us
    if mode == "replaced":
        if item.audio.replacement is None:
            ctx.warn("missing_audio_replacement", "replaced audio has no source", item_id=item.id)
            mode, asset_id, source_in = "muted", None, None
        else:
            asset_id = item.audio.replacement.asset_id
            source_in = item.audio.replacement.source_in_us
    elif mode == "muted":
        asset_id, source_in = None, None
    return ResolvedAudio(
        mode=mode,
        asset_id=asset_id,
        source_in_us=source_in,
        gain_db=item.audio.gain_db,
        fade_in_frames=min(duration, duration_frames(item.audio.fade_in_us, ctx.rate)),
        fade_out_frames=min(duration, duration_frames(item.audio.fade_out_us, ctx.rate)),
    )


def _main_line(ctx: _Context) -> tuple[list[ResolvedClip], list[ResolvedClip], list[BeatSpan]]:
    video: list[ResolvedClip] = []
    audio: list[ResolvedClip] = []
    spans: list[BeatSpan] = []
    position = 0
    for beat in ctx.project.beats:
        if not beat.included:
            continue
        beat_start = position
        for item in beat.cut:
            if not item.enabled:
                continue
            duration = clip_frames(item.source_in_us, item.source_out_us, ctx.rate)
            if duration <= 0:
                ctx.warn(
                    "empty_clip",
                    f"clip is shorter than one frame at {ctx.rate} fps and is skipped",
                    item_id=item.id,
                    beat_id=beat.id,
                )
                continue
            v, a = _main_clip(ctx, beat, item, position, duration)
            video.append(v)
            audio.append(a)
            position += duration
        if position > beat_start:
            spans.append(
                BeatSpan(beat_id=beat.id, start=beat_start, duration=position - beat_start)
            )
    return video, audio, spans


def _main_clip(
    ctx: _Context, beat: Beat, item: ClipItem, start: int, duration: int
) -> tuple[ResolvedClip, ResolvedClip]:
    take = beat.take(item.segment_id) if item.segment_id else None
    asset_duration = ctx.asset_duration(item.asset_id, item.id)
    if asset_duration is not None and item.source_out_us > asset_duration:
        ctx.warn(
            "source_out_of_range",
            f"source out {item.source_out_us} us is past the end of the asset",
            item_id=item.id,
        )
    resolved_audio = _audio(ctx, item, duration)
    video = ResolvedClip(
        item_id=item.id,
        track="V1",
        asset_id=item.asset_id,
        beat_id=beat.id,
        segment_id=item.segment_id,
        take_status=str(take.status) if take else None,
        timeline_start=start,
        duration=duration,
        source_in_us=item.source_in_us,
        source_out_us=item.source_out_us,
        source_in_frame=frames(item.source_in_us, ctx.rate),
        available_before=handles.available_before(item.source_in_us, ctx.rate),
        available_after=handles.available_after(item.source_out_us, asset_duration, ctx.rate),
        audio=resolved_audio,
        fit="fit",
    )
    audio_asset = resolved_audio.asset_id or item.asset_id
    audio_in = (
        item.source_in_us if resolved_audio.source_in_us is None else resolved_audio.source_in_us
    )
    audio_out = audio_in + item.duration_us
    audio_duration = (
        asset_duration if audio_asset == item.asset_id else ctx.asset_duration(audio_asset, item.id)
    )
    audio = video.model_copy(
        update={
            "track": "A1",
            "asset_id": audio_asset,
            "source_in_us": audio_in,
            "source_out_us": audio_out,
            "source_in_frame": frames(audio_in, ctx.rate),
            "available_before": handles.available_before(audio_in, ctx.rate),
            "available_after": handles.available_after(audio_out, audio_duration, ctx.rate),
            "fit": None,
        }
    )
    return video, audio


# --------------------------------------------------------------------------- transitions


def _alignment(ctx: _Context, tr: Transition) -> handles.AlignmentName:
    if is_unknown(tr.alignment) or tr.alignment not in handles.ALIGNMENTS:
        ctx.warn(
            "unknown_alignment",
            f"alignment {tr.alignment!r} is not supported; using center",
            transition_id=tr.id,
        )
        return "center"
    return tr.alignment  # type: ignore[return-value]


def _dormant(tr: Transition, alignment: str) -> ResolvedTransition:
    return ResolvedTransition(
        transition_id=tr.id,
        after_item_id=tr.after_item_id,
        before_item_id=tr.before_item_id,
        type=str(tr.type),
        state="dormant",
        alignment=alignment,
        params=tr.params,
    )


def _audio_mode(ctx: _Context, tr: Transition, duration: int) -> tuple[str, int]:
    if isinstance(tr.audio, CrossfadeAudio):
        return "crossfade", min(duration, duration_frames(tr.audio.duration_us, ctx.rate))
    if tr.audio == "cut":
        return "cut", 0
    if tr.audio != "follow":
        ctx.warn(
            "unknown_transition_audio",
            f"transition audio {tr.audio!r} is not supported; following the video",
            transition_id=tr.id,
        )
    return "follow", duration


def _transitions(
    ctx: _Context, video: list[ResolvedClip], audio: list[ResolvedClip]
) -> tuple[list[ResolvedTransition], list[ResolvedTransition]]:
    index = {c.item_id: i for i, c in enumerate(video)}
    by_left: dict[int, Transition] = {}
    dormant: list[ResolvedTransition] = []
    for tr in ctx.project.transitions:
        if tr.type == "cut" or duration_frames(tr.duration_us, ctx.rate) <= 0:
            continue  # an explicit hard cut
        i = index.get(tr.after_item_id)
        j = index.get(tr.before_item_id)
        if i is None or j is None or j != i + 1:
            alignment = "center" if is_unknown(tr.alignment) else str(tr.alignment)
            dormant.append(_dormant(tr, alignment))
            ctx.warn(
                "dormant_transition",
                "transition items are not adjacent on the main line; rendered as a hard cut",
                transition_id=tr.id,
                item_id=tr.after_item_id,
            )
            continue
        by_left[i] = tr

    active: list[ResolvedTransition] = []
    used_head = [0] * len(video)  # frames at the head of clip i taken by its incoming transition
    for i in sorted(by_left):
        tr = by_left[i]
        if is_unknown(tr.type):
            ctx.warn(
                "unknown_transition_type",
                f"transition type {tr.type!r} is not supported; exporters fall back to a dissolve",
                transition_id=tr.id,
            )
        alignment = _alignment(ctx, tr)
        left, right = video[i], video[i + 1]
        wanted = duration_frames(tr.duration_us, ctx.rate)
        fit = handles.max_duration(alignment, left.duration - used_head[i], right.duration)
        duration = min(wanted, fit)
        if duration <= 0:
            dormant.append(_dormant(tr, alignment))
            ctx.warn(
                "transition_too_long",
                "transition does not fit between its clips; rendered as a hard cut",
                transition_id=tr.id,
                item_id=tr.after_item_id,
            )
            continue
        if duration < wanted:
            ctx.warn(
                "transition_clamped",
                f"transition shortened from {wanted} to {duration} frames to fit its clips",
                transition_id=tr.id,
                item_id=tr.after_item_id,
            )
        before, after = handles.split(duration, alignment)
        used_head[i + 1] = after
        result = handles.check(
            duration,
            alignment,
            right.available_before,
            left.available_after,
            before_visible=left.duration - used_head[i],
            after_visible=right.duration,
        )
        if not result.ok:
            ctx.warn(
                "insufficient_handles",
                result.describe(),
                transition_id=tr.id,
                item_id=tr.after_item_id,
            )
        for track in (video, audio):
            track[i] = track[i].model_copy(update={"handle_after": after})
            track[i + 1] = track[i + 1].model_copy(update={"handle_before": before})
        audio_mode, audio_frames = _audio_mode(ctx, tr, duration)
        active.append(
            ResolvedTransition(
                transition_id=tr.id,
                after_item_id=tr.after_item_id,
                before_item_id=tr.before_item_id,
                type=str(tr.type),
                state="active",
                alignment=alignment,
                duration=duration,
                cut_frame=right.timeline_start,
                left_frames=before,
                right_frames=after,
                audio=audio_mode,
                audio_duration=audio_frames,
                params=tr.params,
            )
        )
    return active, dormant


# --------------------------------------------------------------------------- overlays


def _fit(overlay: OverlayItem) -> ResolvedFit:
    if isinstance(overlay.fit, FitRect):
        return ResolvedFitRect(x=overlay.fit.x, y=overlay.fit.y, scale=overlay.fit.scale)
    return overlay.fit


def _overlays(ctx: _Context, spans: dict[str, BeatSpan], total: int) -> list[ResolvedClip]:
    clips: list[ResolvedClip] = []
    for overlay in ctx.project.overlays:
        if not overlay.enabled:
            continue
        beat_id: str | None = None
        if isinstance(overlay.anchor, BeatAnchor):
            beat_id = overlay.anchor.beat_id
            span = spans.get(beat_id)
            if span is None:
                ctx.warn(
                    "overlay_dropped",
                    "anchor beat is not on the main line",
                    item_id=overlay.id,
                    beat_id=beat_id,
                )
                continue
            start = span.start + duration_frames(overlay.anchor.offset_us, ctx.rate)
        else:
            start = frames(overlay.anchor.time_us, ctx.rate)
        source_in = frames(overlay.source_in_us, ctx.rate)
        duration = clip_frames(overlay.source_in_us, overlay.source_out_us, ctx.rate)
        clamped = False
        if start < 0:
            start, clamped = 0, True
        if start + duration > total:
            duration, clamped = total - start, True
        if duration <= 0:
            ctx.warn(
                "overlay_dropped",
                "overlay falls outside the main line",
                item_id=overlay.id,
                beat_id=beat_id,
            )
            continue
        if clamped:
            ctx.warn(
                "overlay_clamped",
                "overlay moved or shortened to stay within the main line",
                item_id=overlay.id,
                beat_id=beat_id,
            )
        source_out = (
            overlay.source_out_us
            if not clamped
            else min(overlay.source_out_us, frame_to_us(source_in + duration, ctx.rate))
        )
        asset_duration = ctx.asset_duration(overlay.asset_id, overlay.id)
        clips.append(
            ResolvedClip(
                item_id=overlay.id,
                track=overlay.track,
                asset_id=overlay.asset_id,
                beat_id=beat_id,
                timeline_start=start,
                duration=duration,
                source_in_us=overlay.source_in_us,
                source_out_us=source_out,
                source_in_frame=source_in,
                available_before=handles.available_before(overlay.source_in_us, ctx.rate),
                available_after=handles.available_after(source_out, asset_duration, ctx.rate),
                audio=ResolvedAudio(
                    mode=overlay.audio.mode,
                    asset_id=overlay.asset_id if overlay.audio.mode != "muted" else None,
                    source_in_us=overlay.source_in_us if overlay.audio.mode != "muted" else None,
                    gain_db=overlay.audio.gain_db,
                ),
                fit=_fit(overlay),
                clamped=clamped,
            )
        )
    clips.sort(key=lambda c: (c.timeline_start, c.item_id))
    return clips


# --------------------------------------------------------------------------- markers


def _source_frame(clip: ResolvedClip, time_us: Micros, rate: Rational) -> int | None:
    if not clip.source_in_us <= time_us < clip.source_out_us:
        return None
    offset = frames(time_us, rate) - clip.source_in_frame
    return clip.timeline_start + min(max(offset, 0), clip.duration - 1)


def _markers(ctx: _Context, placed: Iterable[ResolvedClip]) -> list[ResolvedMarker]:
    clips = list(placed)
    result: list[ResolvedMarker] = []
    for marker in ctx.project.markers:
        target = marker.target
        hits: list[tuple[int, str | None]] = []
        if isinstance(target, TimelineMarkerTarget):
            hits.append((frames(marker.time_us, ctx.rate), None))
        elif isinstance(target, ItemMarkerTarget | AssetMarkerTarget):
            for clip in clips:
                match = (
                    clip.item_id == target.item_id
                    if isinstance(target, ItemMarkerTarget)
                    else clip.asset_id == target.asset_id
                )
                frame = _source_frame(clip, marker.time_us, ctx.rate) if match else None
                if frame is not None:
                    hits.append((frame, clip.item_id))
        result.extend(
            ResolvedMarker(
                marker_id=marker.id, frame=f, note=marker.note, color=marker.color, item_id=item_id
            )
            for f, item_id in hits
        )
    result.sort(key=lambda m: (m.frame, m.marker_id, m.item_id or ""))
    return result


# --------------------------------------------------------------------------- entry point


def resolve(project: Project) -> ResolvedTimeline:
    """Resolve the project's decisions into a flat, frame-quantised timeline."""
    from videoflow.editor.resolve import document_for, resolve_editor

    document = document_for(project)
    if document is not None:
        return resolve_editor(project, document)
    ctx = _Context(project)
    video, audio, spans = _main_line(ctx)
    total = sum(c.duration for c in video)
    active, dormant = _transitions(ctx, video, audio)
    overlays = _overlays(ctx, {s.beat_id: s for s in spans}, total)
    tracks = [
        ResolvedTrack(id="V1", kind="video", clips=video),
        ResolvedTrack(id="A1", kind="audio", clips=audio),
        ResolvedTrack(id="V2", kind="video", clips=[c for c in overlays if c.track == "V2"]),
    ]
    other = sorted({str(c.track) for c in overlays if c.track != "V2"})
    for track_id in other:
        kind = "audio" if track_id.startswith("A") else "video"
        clips = [c for c in overlays if c.track == track_id]
        tracks.append(ResolvedTrack(id=track_id, kind=kind, clips=clips))
    settings = project.settings
    timeline = ResolvedTimeline(
        project_id=project.id,
        revision=project.revision,
        rate=ctx.rate,
        width=settings.width,
        height=settings.height,
        sample_rate=settings.sample_rate,
        duration=total,
        tracks=tracks,
        transitions=active,
        dormant_transitions=dormant,
        beats=spans,
        markers=_markers(ctx, video + overlays),
        warnings=ctx.warnings,
    )
    timeline.warnings.extend(overlap_warnings(timeline))
    return timeline
