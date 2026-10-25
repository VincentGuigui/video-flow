"""Join cached words to the audible edit, applying authored transcript corrections."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from videoflow.analysis.types import Transcript, Word
from videoflow.core.time import frame_to_us
from videoflow.project.models import Project
from videoflow.timeline.resolved import ResolvedClip, ResolvedTimeline

type Transcripts = Mapping[str, Transcript]


@dataclass(frozen=True)
class EditWord:
    text: str
    start_us: int
    end_us: int
    item_id: str
    clip_end_us: int


def source_words(project: Project, asset_id: str, transcripts: Transcripts) -> list[Word]:
    transcript = transcripts.get(asset_id)
    words = list(transcript.words) if transcript else []
    for edit in project.overrides.transcript_edits:
        if edit.asset_id != asset_id:
            continue
        words = [
            w
            for w in words
            if not (w.start_us < edit.range.end_us and w.end_us > edit.range.start_us)
        ]
        tokens = edit.text.split()
        span = edit.range.duration_us
        # Corrections have no word timings; distribute within the authored source range.
        words.extend(
            Word(
                text=text,
                start_us=edit.range.start_us + span * i // len(tokens),
                end_us=edit.range.start_us + span * (i + 1) // len(tokens),
            )
            for i, text in enumerate(tokens)
        )
    return sorted(words, key=lambda w: (w.start_us, w.end_us))


def clip_words(
    clip: ResolvedClip, resolved: ResolvedTimeline, words: Sequence[Word]
) -> list[EditWord]:
    start = frame_to_us(clip.timeline_start, resolved.rate)
    end = frame_to_us(clip.timeline_end, resolved.rate)
    result = []
    for word in words:
        a, b = max(word.start_us, clip.source_in_us), min(word.end_us, clip.source_out_us)
        if b <= a or not word.text.strip():
            continue
        mapped_start = max(start, min(end, start + a - clip.source_in_us))
        mapped_end = max(start, min(end, start + b - clip.source_in_us))
        if mapped_end > mapped_start:
            result.append(EditWord(word.text.strip(), mapped_start, mapped_end, clip.item_id, end))
    return result


def edit_words(
    resolved: ResolvedTimeline, project: Project, transcripts: Transcripts
) -> list[EditWord]:
    track = resolved.track("A1")
    if track is None:
        return []
    result = []
    for clip in track.clips:
        asset = project.asset(clip.asset_id)
        if (clip.audio and clip.audio.mode == "muted") or (asset and not asset.probe.has_audio):
            continue
        result.extend(clip_words(clip, resolved, source_words(project, clip.asset_id, transcripts)))
    return result
