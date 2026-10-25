"""Word-timed SRT: frame-resolved cuts, no cue overlap, at most 2 × 42 characters."""

import re
import textwrap

from videoflow.analysis.textnorm import FILLERS
from videoflow.exporters.transcript import EditWord, Transcripts, edit_words
from videoflow.project.models import Project
from videoflow.timeline.resolved import ResolvedTimeline


def _stamp(us: int) -> str:
    millis = max(0, (us + 500) // 1000)
    seconds, ms = divmod(millis, 1000)
    minutes, sec = divmod(seconds, 60)
    hour, minute = divmod(minutes, 60)
    return f"{hour:02d}:{minute:02d}:{sec:02d},{ms:03d}"


def _wrap(text: str) -> list[str]:
    return textwrap.wrap(text, width=42, break_long_words=True, break_on_hyphens=False)


def export_srt(resolved: ResolvedTimeline, project: Project, transcripts: Transcripts) -> str:
    fillers = FILLERS.get(project.settings.language.split("-")[0], frozenset())
    words = [
        w
        for w in edit_words(resolved, project, transcripts)
        if re.sub(r"[^\w]", "", w.text.casefold()) not in fillers
    ]
    # A pathological token longer than a cue is split, keeping every cue within the limit.
    expanded = []
    for word in words:
        chunks = textwrap.wrap(word.text, width=84, break_long_words=True, break_on_hyphens=False)
        for i, text in enumerate(chunks):
            duration = word.end_us - word.start_us
            expanded.append(
                EditWord(
                    text,
                    word.start_us + duration * i // len(chunks),
                    word.start_us + duration * (i + 1) // len(chunks),
                    word.item_id,
                    word.clip_end_us,
                )
            )
    groups: list[list[EditWord]] = []
    current: list[EditWord] = []
    for word in expanded:
        text = " ".join([*(w.text for w in current), word.text])
        if current and (
            word.item_id != current[-1].item_id
            or word.start_us - current[-1].end_us > 600_000
            or word.end_us - current[0].start_us > 6_000_000
            or current[-1].text.endswith((".", "!", "?"))
            or len(_wrap(text)) > 2
        ):
            groups.append(current)
            current = []
        current.append(word)
    if current:
        groups.append(current)
    cues: list[str] = []
    for i, group in enumerate(groups):
        start = group[0].start_us
        end = min(max(group[-1].end_us, start + 1_000_000), group[-1].clip_end_us)
        if i + 1 < len(groups):
            end = min(end, groups[i + 1][0].start_us)
        if (end + 500) // 1000 <= (start + 500) // 1000:
            continue
        text = "\n".join(_wrap(" ".join(w.text for w in group)))
        cues.append(f"{len(cues) + 1}\n{_stamp(start)} --> {_stamp(end)}\n{text}\n")
    return "\n".join(cues)
