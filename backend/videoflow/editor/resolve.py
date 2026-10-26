"""Resolve the interactive document into the common exporter/render contract."""

from videoflow.core.time import frame_to_us, frames
from videoflow.editor.models import EditorClip, EditorDocument, Transform
from videoflow.editor.transitions import active_transitions
from videoflow.project.models import Project, ProjectSettings, VideoStreamInfo
from videoflow.timeline.resolved import (
    ResolvedAudio,
    ResolvedClip,
    ResolvedTimeline,
    ResolvedTrack,
    ResolvedTransition,
    TimelineWarning,
)


def document_for(project: Project) -> EditorDocument | None:
    raw = (project.__pydantic_extra__ or {}).get("editor")
    return EditorDocument.model_validate(raw) if raw is not None else None


def fit_transform(settings: ProjectSettings, video: VideoStreamInfo | None) -> Transform:
    """Fit the upright picture, matching FFmpeg's autorotation and SDR proxies."""
    if video is None:
        return Transform(width=settings.width, height=settings.height)
    width, height = video.width, video.height
    if video.rotation in (90, 270):
        width, height = height, width
    factor = min(settings.width / width, settings.height / height)
    return Transform(
        width=width * factor,
        height=height * factor,
        x=(settings.width - width * factor) / 2,
        y=(settings.height - height * factor) / 2,
    )


def editable_document(project: Project) -> EditorDocument:
    """Import legacy authored cuts without silently discarding an existing edit."""
    from videoflow.editor.models import EditorClip
    from videoflow.timeline.resolve import resolve

    existing = document_for(project)
    if existing is not None:
        return existing
    timeline = resolve(project)
    clips = []
    for track in timeline.tracks:
        for c in track.clips:
            asset = project.asset(c.asset_id)
            kind = "video" if track.kind == "video" else "audio"
            if asset is None or (
                kind == "audio"
                and (not asset.probe.has_audio or (c.audio and c.audio.mode == "muted"))
            ):
                continue
            # Legacy replacement audio is already independent in the resolved tracks.
            link = None
            if c.audio and c.audio.mode == "linked" and asset.probe.video and asset.probe.has_audio:
                link = f"legacy_{c.item_id}"
            clips.append(
                EditorClip(
                    id=f"{c.item_id}_{track.id}",
                    kind=kind,
                    asset_id=c.asset_id,
                    name=asset.path.replace("\\", "/").split("/")[-1],
                    start=c.timeline_start,
                    source_in=c.source_in_frame,
                    source_out=c.source_in_frame + c.duration,
                    layer=0 if track.id in ("V1", "A1") else 1,
                    link_id=link,
                    gain_db=c.audio.gain_db if c.audio else 0,
                    transform=fit_transform(project.settings, asset.probe.video),
                )
            )
    return EditorDocument(clips=clips)


def validate_assets(document: EditorDocument, project: Project) -> None:
    for clip in document.clips:
        if clip.kind == "gap":
            continue
        asset = project.asset(clip.asset_id or "")
        if asset is None:
            raise ValueError(f"Unknown asset {clip.asset_id}")
        if clip.source_out > frames(asset.probe.duration_us, project.settings.frame_rate):
            raise ValueError(f"Clip {clip.name} exceeds its source duration")
        if clip.kind == "video" and asset.probe.video is None:
            raise ValueError(f"{clip.name} has no video")
        if clip.kind == "audio" and not asset.probe.has_audio:
            raise ValueError(f"{clip.name} has no audio")


def resolve_editor(project: Project, document: EditorDocument) -> ResolvedTimeline:
    settings = project.settings
    rate = settings.frame_rate

    def source_frames(clip: EditorClip) -> int:
        asset = project.asset(clip.asset_id or "")
        return frames(asset.probe.duration_us, rate) if asset else clip.source_out

    clips, duration, active = active_transitions(document, source_frames)
    tracks: list[ResolvedTrack] = []
    warnings: list[TimelineWarning] = []
    base = min((c.layer for c in clips if c.kind == "video"), default=0)
    transitions: list[ResolvedTransition] = []
    for item in active:
        t = item.transition
        if next(c for c in clips if c.id == t.left_id).layer != base:
            warnings.append(
                TimelineWarning(
                    code="editor_transition_layer",
                    message=f"Transition {t.id} is above V1: rendered, not exported.",
                )
            )
            continue
        transitions.append(
            ResolvedTransition(
                transition_id=t.id,
                after_item_id=t.left_id,
                before_item_id=t.right_id,
                type=t.type,
                state="active",
                duration=item.duration,
                cut_frame=item.cut,
                left_frames=item.before,
                right_frames=item.after,
                audio_duration=item.duration,
            )
        )
    if transitions:
        warnings.append(
            TimelineWarning(
                code="editor_transition_audio",
                message="Audio crossfades of transitions are rendered but not exported.",
            )
        )
    for kind in ("audio", "video"):
        layers = sorted({c.layer for c in clips if c.kind == kind or c.kind == "gap"})
        for index, layer in enumerate(layers):
            track_id = ("A" if kind == "audio" else "V") + str(index + 1)
            resolved = []
            for clip in sorted(clips, key=lambda c: (c.start, c.id)):
                if clip.layer != layer or clip.kind not in (kind, "gap"):
                    continue
                asset = project.asset(clip.asset_id or "")
                source_duration = frames(asset.probe.duration_us, rate) if asset else clip.duration
                resolved.append(
                    ResolvedClip(
                        item_id=clip.id,
                        track=track_id,
                        asset_id=clip.asset_id or "__gap__",
                        timeline_start=clip.start,
                        duration=clip.duration,
                        source_in_frame=clip.source_in,
                        source_in_us=frame_to_us(clip.source_in, rate),
                        source_out_us=frame_to_us(clip.source_out, rate),
                        available_before=clip.source_in,
                        available_after=max(0, source_duration - clip.source_out),
                        audio=ResolvedAudio(
                            mode="muted" if clip.kind != "audio" else "linked",
                            asset_id=clip.asset_id,
                            gain_db=clip.gain_db,
                        ),
                        kind="gap" if clip.kind == "gap" else "media",
                        transform=clip.transform.dump(),
                        layer=clip.layer,
                    )
                )
            tracks.append(ResolvedTrack(id=track_id, kind=kind, clips=resolved))
    if any(c.kind == "video" for c in clips):
        warnings.append(
            TimelineWarning(
                code="editor_transforms", message="Spatial transforms are metadata in OTIO exports."
            )
        )
    return ResolvedTimeline(
        project_id=project.id,
        revision=project.revision,
        rate=rate,
        width=settings.width,
        height=settings.height,
        sample_rate=settings.sample_rate,
        duration=duration,
        tracks=tracks,
        transitions=transitions,
        warnings=warnings,
    )
