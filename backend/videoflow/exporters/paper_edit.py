"""One readable row per visible main-line clip, in edit order."""

import csv
import io

from videoflow.core.time import format_timecode
from videoflow.exporters.transcript import Transcripts, clip_words, source_words
from videoflow.project.models import Project
from videoflow.timeline.resolved import ResolvedTimeline

HEADERS = ("Order", "Beat", "Asset", "Source in", "Source out", "Duration", "Transcript")


def paper_rows(
    resolved: ResolvedTimeline, project: Project, transcripts: Transcripts
) -> list[list[str]]:
    video, audio = resolved.track("V1"), resolved.track("A1")
    audio_by_id = {c.item_id: c for c in audio.clips} if audio else {}
    labels = {b.id: b.label for b in project.beats}
    rows = []
    for i, clip in enumerate(video.clips if video else [], 1):
        asset = project.asset(clip.asset_id)
        speech = audio_by_id.get(clip.item_id, clip)
        words = clip_words(speech, resolved, source_words(project, speech.asset_id, transcripts))
        text = " ".join(w.text for w in words)
        if speech.audio and speech.audio.mode == "muted":
            text = ""
        rows.append(
            [
                str(i),
                labels.get(clip.beat_id or "", ""),
                asset.path if asset else clip.asset_id,
                format_timecode(clip.source_in_frame, resolved.rate),
                format_timecode(clip.source_in_frame + clip.duration, resolved.rate),
                format_timecode(clip.duration, resolved.rate),
                text,
            ]
        )
    return rows


def export_csv(resolved: ResolvedTimeline, project: Project, transcripts: Transcripts) -> str:
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(HEADERS)
    writer.writerows(paper_rows(resolved, project, transcripts))
    return buffer.getvalue()


def export_markdown(resolved: ResolvedTimeline, project: Project, transcripts: Transcripts) -> str:
    def escape(text: str) -> str:
        return (
            " ".join(text.split())
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace("\\", "\\\\")
            .replace("|", "\\|")
        )

    lines = [
        f"# {escape(project.name)} — paper edit",
        "",
        f"Rate: {resolved.rate} fps; timecodes are non-drop.",
        "",
        "| " + " | ".join(HEADERS) + " |",
        "| " + " | ".join("---" for _ in HEADERS) + " |",
    ]
    lines.extend(
        "| " + " | ".join(escape(v) for v in row) + " |"
        for row in paper_rows(resolved, project, transcripts)
    )
    return "\n".join(lines) + "\n"
