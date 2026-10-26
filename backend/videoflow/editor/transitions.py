"""Plan editor transitions: centred on the cut, total duration unchanged.

A cross dissolve overlaps the two clips around the cut, using source frames beyond
the cut (handles): the left clip continues `after` frames past the cut and the right
clip starts `before` frames early, fading in over the left. Linked audio follows and
crossfades. A dip fades the whole picture to a colour and back without handles; the
audio dips with it. Missing handles or short clips shorten the transition.
"""

from collections.abc import Callable
from dataclasses import dataclass, field

from videoflow.editor.models import EditorClip, EditorDocument, EditorTransition, layout

DIP_COLORS = {"dip_black": "black", "dip_white": "white"}


@dataclass(frozen=True)
class ActiveTransition:
    transition: EditorTransition
    cut: int
    before: int
    after: int

    @property
    def duration(self) -> int:
        return self.before + self.after

    @property
    def shortened(self) -> bool:
        return self.duration < self.transition.duration


@dataclass(frozen=True)
class Dip:
    start: int
    before: int
    after: int
    color: str


@dataclass
class TransitionPlan:
    clips: list[EditorClip]
    total: int
    active: list[ActiveTransition] = field(default_factory=list)
    video_fade_in: dict[str, int] = field(default_factory=dict)
    audio_fades: dict[str, tuple[int, int]] = field(default_factory=dict)
    dips: list[Dip] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def active_transitions(
    document: EditorDocument, source_frames: Callable[[EditorClip], int]
) -> tuple[list[EditorClip], int, list[ActiveTransition]]:
    clips, total = layout(document)
    by_id = {c.id: c for c in clips}
    seen: set[tuple[str, str]] = set()
    active: list[ActiveTransition] = []
    for t in document.transitions:
        left, right = by_id.get(t.left_id), by_id.get(t.right_id)
        if (
            left is None
            or right is None
            or left.kind != "video"
            or right.kind != "video"
            or left.layer != right.layer
            or left.start + left.duration != right.start
            or (t.left_id, t.right_id) in seen
        ):
            continue
        seen.add((t.left_id, t.right_id))
        half = t.duration // 2
        if t.type == "dissolve":
            before = min(half, right.source_in, left.duration)
            after = min(t.duration - half, source_frames(left) - left.source_out, right.duration)
        else:
            before = min(half, left.duration)
            after = min(t.duration - half, right.duration)
        before, after = max(0, before), max(0, after)
        if before + after:
            active.append(ActiveTransition(t, right.start, before, after))
    return clips, total, active


def plan_transitions(
    document: EditorDocument, source_frames: Callable[[EditorClip], int]
) -> TransitionPlan:
    clips, total, active = active_transitions(document, source_frames)
    plan = TransitionPlan(clips=[], total=total, active=active)
    partners: dict[str, str] = {}
    for c in clips:
        if c.link_id:
            other = next((o for o in clips if o.link_id == c.link_id and o.id != c.id), None)
            if other is not None:
                partners[c.id] = other.id
    updates: dict[str, dict[str, int]] = {}

    def update(clip_id: str, **values: int) -> None:
        for target in (clip_id, partners.get(clip_id)):
            if target is not None:
                entry = updates.setdefault(target, {})
                for key, value in values.items():
                    entry[key] = entry.get(key, 0) + value

    def audio_fade(clip_id: str, fade_in: int = 0, fade_out: int = 0) -> None:
        audio = partners.get(clip_id)
        if audio is None:
            return
        current = plan.audio_fades.get(audio, (0, 0))
        plan.audio_fades[audio] = (max(current[0], fade_in), max(current[1], fade_out))

    for item in active:
        t = item.transition
        if item.shortened:
            plan.warnings.append(
                f"Transition {t.id} shortened to {item.duration} frames "
                f"(requested {t.duration}): not enough source media or clip length"
            )
        if t.type == "dissolve":
            update(t.left_id, source_out=item.after)
            update(t.right_id, start=-item.before, source_in=-item.before)
            plan.video_fade_in[t.right_id] = item.duration
            audio_fade(t.left_id, fade_out=item.duration)
            audio_fade(t.right_id, fade_in=item.duration)
        else:
            plan.dips.append(
                Dip(item.cut - item.before, item.before, item.after, DIP_COLORS[t.type])
            )
            audio_fade(t.left_id, fade_out=item.before)
            audio_fade(t.right_id, fade_in=item.after)
    for c in clips:
        delta = updates.get(c.id)
        plan.clips.append(
            c.model_copy(
                update={
                    "start": c.start + delta.get("start", 0),
                    "source_in": c.source_in + delta.get("source_in", 0),
                    "source_out": c.source_out + delta.get("source_out", 0),
                }
            )
            if delta
            else c
        )
    return plan
