"""CMX 3600 V1 writer with explicit reel mapping and dissolve event pairs."""

from dataclasses import dataclass

from videoflow.core.time import format_timecode
from videoflow.project.models import Project
from videoflow.timeline.resolved import ResolvedTimeline


@dataclass
class EdlResult:
    text: str
    reels: dict[str, str]
    warnings: list[str]


def _line(text: str) -> str:
    return " ".join(text.split())


def export_edl(resolved: ResolvedTimeline, project: Project) -> EdlResult:
    track = resolved.track("V1")
    clips = track.clips if track else []
    if len(clips) > 999:
        raise ValueError("CMX 3600 supports at most 999 events")
    assets = {a.id: a for a in project.assets}
    ids = sorted({c.asset_id for c in clips})
    reel_ids = {asset_id: f"R{i:07d}" for i, asset_id in enumerate(ids, 1)}
    reels = {reel_ids[i]: assets[i].path if i in assets else i for i in ids}
    warnings = ["EDL includes V1 only; audio, overlays, gain and fades are omitted."]
    by_id = {c.item_id: c for c in clips}
    active = []
    for tr in resolved.transitions:
        left, right = by_id[tr.after_item_id], by_id[tr.before_item_id]
        if left.freeze_after or right.freeze_before:
            warnings.append(
                f"Transition {tr.transition_id}: missing source handles; exported as a hard cut."
            )
        else:
            active.append(tr)
    transitions = {t.before_item_id: t for t in active}
    outgoing = {t.after_item_id: t for t in active}
    if resolved.rate.is_ntsc:
        warnings.append(f"{resolved.rate} fps is written as non-drop timecode.")
    lines = [f"TITLE: {_line(project.name)}", "FCM: NON-DROP FRAME", ""]
    for index, clip in enumerate(clips, 1):
        incoming = transitions.get(clip.item_id)
        next_transition = outgoing.get(clip.item_id)
        before = incoming.left_frames if incoming else 0
        record_in = clip.timeline_start - before
        record_out = clip.timeline_end - (next_transition.left_frames if next_transition else 0)
        source_in = clip.source_in_frame - before
        source_out = source_in + record_out - record_in

        def event(
            reel: str, code: str, si: int, so: int, ri: int, ro: int, number: int = index
        ) -> str:
            times = " ".join(format_timecode(v, resolved.rate) for v in (si, so, ri, ro))
            return f"{number:03d}  {reel:8} V     {code:8} {times}"

        if incoming:
            if incoming.duration > 999:
                raise ValueError("CMX 3600 dissolve duration cannot exceed 999 frames")
            left = clips[index - 2]
            boundary = left.source_in_frame + left.duration - before
            # CMX requires an A-side C and B-side D with the SAME event number.
            lines.append(
                event(reel_ids[left.asset_id], "C", boundary, boundary, record_in, record_in)
            )
            code = f"D {incoming.duration:03d}"
            if incoming.type != "dissolve":
                warnings.append(f"Transition {incoming.transition_id}: {incoming.type} → dissolve.")
        else:
            code = "C"
        lines.append(
            event(reel_ids[clip.asset_id], code, source_in, source_out, record_in, record_out)
        )
        name = _line(assets[clip.asset_id].path) if clip.asset_id in assets else clip.asset_id
        if incoming:
            previous_id = clips[index - 2].asset_id
            previous = _line(assets[previous_id].path) if previous_id in assets else previous_id
            lines.extend([f"* FROM CLIP NAME: {previous}", f"* FROM CLIP: {previous}"])
        direction = "TO" if incoming else "FROM"
        lines.extend([f"* {direction} CLIP NAME: {name}", f"* {direction} CLIP: {name}"])
        lines.append(f"* VIDEOFLOW ITEM: {clip.item_id}")
        lines.append("")
    for marker in resolved.markers:
        lines.append(
            f"* MARKER {format_timecode(marker.frame, resolved.rate)} {_line(marker.note)}"
        )
    # Readers collect comments after events; leading mapping comments break some adapters.
    if clips:
        lines.extend(f"* REEL {reel}: {_line(path)}" for reel, path in reels.items())
    return EdlResult("\n".join(lines) + "\n", reels, warnings)
