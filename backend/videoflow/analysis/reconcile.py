"""Reconcile analysis proposals with the accepted beats of ``project.json`` (08 §3, 04 §10).

Proposals live in the analysis cache; beats in the project are decisions. On every
re-run:

* **Locked** beats (any user decision locks a beat) are kept exactly as they are, at
  their position; their segments are withdrawn from the proposals.
* Dismissed segments (``overrides.dismissed_segment_ids``) are withdrawn too.
* Each remaining unlocked beat is matched to the proposal sharing the most segments
  (greedy, deterministic); it keeps its id and ``included`` flag and takes the proposal's
  label, role, takes and default selection. Its cut is kept when the selected take did
  not change, so transitions stay attached.
* Unmatched proposals become new beats; unmatched unlocked beats are removed (their
  transitions turn dormant, they are never deleted implicitly).
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field

from videoflow.analysis.types import Proposal, ProposedBeat, Segment
from videoflow.core import ids
from videoflow.core.time import TimeRange
from videoflow.project.models import Beat, ClipAudio, ClipItem, Project, TakeRef


@dataclass
class ReconcileReport:
    kept_locked: list[str] = field(default_factory=list)
    updated: dict[str, str] = field(default_factory=dict)
    """Existing beat id -> proposal key."""
    created: dict[str, str] = field(default_factory=dict)
    """Proposal key -> new beat id."""
    removed: list[str] = field(default_factory=list)
    withdrawn: list[str] = field(default_factory=list)
    """Proposed segment ids skipped: in a locked beat, dismissed, or unknown."""


def _cut_item(
    project: Project,
    take: TakeRef,
    previous: ClipItem | None,
    new_clip_id: Callable[[], str],
) -> list[ClipItem]:
    asset = project.asset(take.asset_id)
    pad = project.settings.clip_padding
    duration = asset.probe.duration_us if asset is not None else take.range.end_us + pad.after_us
    source_in = max(0, take.range.start_us - pad.before_us)
    source_out = min(duration, take.range.end_us + pad.after_us)
    if source_out <= source_in:
        return []
    audio = previous.audio.model_copy(deep=True) if previous is not None else ClipAudio()
    return [
        ClipItem(
            id=new_clip_id(),
            asset_id=take.asset_id,
            segment_id=take.segment_id,
            source_in_us=source_in,
            source_out_us=source_out,
            audio=audio,
        )
    ]


def _build_beat(
    project: Project,
    proposed: ProposedBeat,
    segment_ids: list[str],
    segments: Mapping[str, Segment],
    existing: Beat | None,
    new_beat_id: Callable[[], str],
    new_clip_id: Callable[[], str],
) -> Beat:
    selected = (
        proposed.best_segment_id if proposed.best_segment_id in segment_ids else segment_ids[0]
    )
    takes = [
        TakeRef(
            segment_id=sid,
            asset_id=segments[sid].asset_id,
            range=TimeRange(start_us=segments[sid].start_us, end_us=segments[sid].end_us),
            status="selected" if sid == selected else "alternate",
        )
        for sid in segment_ids
    ]
    sel = next(t for t in takes if t.status == "selected")
    previous = existing.cut[0] if existing is not None and existing.cut else None
    if existing is not None and previous is not None and previous.segment_id == selected:
        cut = [c.model_copy(deep=True) for c in existing.cut]
    else:
        cut = _cut_item(project, sel, previous, new_clip_id)
    return Beat(
        id=existing.id if existing is not None else new_beat_id(),
        label=proposed.label,
        summary=proposed.summary,
        role=proposed.role,
        kind=proposed.kind,
        included=existing.included if existing is not None else True,
        locked=False,
        takes=takes,
        cut=cut,
    )


def reconcile(
    project: Project,
    proposal: Proposal,
    segments: Mapping[str, Segment],
    new_beat_id: Callable[[], str] = lambda: ids.new_id(ids.BEAT),
    new_clip_id: Callable[[], str] = lambda: ids.new_id(ids.CLIP),
) -> tuple[Project, ReconcileReport]:
    """Return a new project whose beats merge ``proposal`` into the accepted beats."""
    out = project.model_copy(deep=True)
    report = ReconcileReport()
    locked_pos = [(i, b) for i, b in enumerate(out.beats) if b.locked]
    claimed = {t.segment_id for _, b in locked_pos for t in b.takes}
    dismissed = set(out.overrides.dismissed_segment_ids)
    report.kept_locked = [b.id for _, b in locked_pos]

    proposals: list[tuple[ProposedBeat, list[str]]] = []
    for pb in proposal.beats:
        keep: list[str] = []
        for sid in pb.segment_ids:
            if sid in claimed or sid in dismissed or sid not in segments:
                report.withdrawn.append(sid)
            elif sid not in keep:
                keep.append(sid)
        if keep:
            proposals.append((pb, keep))

    unlocked = [b for b in out.beats if not b.locked]
    candidates: list[tuple[int, int, int]] = []
    for bi, beat in enumerate(unlocked):
        have = {t.segment_id for t in beat.takes}
        for pi, (_, seg_ids) in enumerate(proposals):
            overlap = len(have.intersection(seg_ids))
            if overlap:
                candidates.append((-overlap, bi, pi))
    match: dict[int, Beat] = {}
    used: set[int] = set()
    for _, bi, pi in sorted(candidates):
        if bi in used or pi in match:
            continue
        used.add(bi)
        match[pi] = unlocked[bi]

    fresh: list[Beat] = []
    for pi, (pb, seg_ids) in enumerate(proposals):
        existing = match.get(pi)
        beat = _build_beat(out, pb, seg_ids, segments, existing, new_beat_id, new_clip_id)
        if existing is not None:
            report.updated[existing.id] = pb.key
        else:
            report.created[pb.key] = beat.id
        fresh.append(beat)
    report.removed = [b.id for bi, b in enumerate(unlocked) if bi not in used]

    beats = fresh
    for pos, beat in locked_pos:
        beats.insert(min(pos, len(beats)), beat)
    out.beats = beats
    return out, report
