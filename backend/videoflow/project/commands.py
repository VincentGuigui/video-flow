"""Semantic edit commands addressed by id (the single undo model, 08 §1 "Undo owner").

Every command is a pure function: ``cmd.apply(project) -> (new_project, inverse)``. The
input project is never mutated. Applying ``inverse`` to ``new_project`` gives back a
project equal to the input (revision excluded: revisions are bumped by
:func:`apply_batch`, once per batch).

The client owns the undo stack: it sends ``{base_revision, commands[]}``, receives the
inverses (already in undo order) and undoes by sending them as a new batch.

Inverses of beat-level edits are snapshots (``PutBeat`` plus ``PutTransition`` /
``PutMarker`` for what moved), which keeps them exact whatever the edit did. Put* commands
are upserts by id: replace in place when the id exists, otherwise insert at ``index``
(append when ``None``).
"""

from abc import abstractmethod
from typing import Annotated, Literal, Protocol

from pydantic import ConfigDict, Field, TypeAdapter

from videoflow.core import ids
from videoflow.core.base import CamelModel
from videoflow.core.time import Micros, NonNegativeMicros
from videoflow.editor.models import EditorDocument
from videoflow.project.models import (
    Asset,
    AssetMarkerTarget,
    Beat,
    BeatAnchor,
    BeatRole,
    ClipAudio,
    ClipItem,
    GroupingConstraint,
    ItemMarkerTarget,
    Marker,
    OverlayItem,
    Project,
    ProjectSettings,
    SyncGroup,
    TranscriptEdit,
    Transition,
)


class CommandError(ValueError):
    """A command's precondition does not hold (unknown id, invalid range, ...)."""


class _HasId(Protocol):
    id: str


# --------------------------------------------------------------------------- helpers


def _index[T: _HasId](items: list[T], item_id: str, kind: str) -> int:
    for i, item in enumerate(items):
        if item.id == item_id:
            return i
    raise CommandError(f"unknown {kind} {item_id}")


def _put[T: _HasId](items: list[T], entity: T, index: int | None) -> tuple[T | None, int]:
    """Upsert by id. Returns (previous entity or None, position)."""
    for i, item in enumerate(items):
        if item.id == entity.id:
            items[i] = entity
            return item, i
    pos = len(items) if index is None else max(0, min(index, len(items)))
    items.insert(pos, entity)
    return None, pos


def _pop[T: _HasId](items: list[T], item_id: str, kind: str) -> tuple[T, int]:
    i = _index(items, item_id, kind)
    return items.pop(i), i


def _beat(p: Project, beat_id: str) -> Beat:
    beat = p.beat(beat_id)
    if beat is None:
        raise CommandError(f"unknown beat {beat_id}")
    return beat


def _item(p: Project, item_id: str) -> tuple[Beat, int, ClipItem]:
    found = p.find_item(item_id)
    if found is None:
        raise CommandError(f"unknown clip item {item_id}")
    beat, i = found
    return beat, i, beat.cut[i]


def _asset(p: Project, asset_id: str) -> Asset:
    asset = p.asset(asset_id)
    if asset is None:
        raise CommandError(f"unknown asset {asset_id}")
    return asset


def _all_item_ids(p: Project) -> set[str]:
    return {c.id for b in p.beats for c in b.cut}


def _check_source_range(p: Project, asset_id: str, source_in: int, source_out: int) -> None:
    asset = _asset(p, asset_id)
    if not 0 <= source_in < source_out <= asset.probe.duration_us:
        raise CommandError(
            f"source range [{source_in}, {source_out}) outside asset {asset_id} "
            f"(duration {asset.probe.duration_us})"
        )


def _snapshot(beat: Beat) -> "PutBeat":
    return PutBeat(beat=beat.model_copy(deep=True))


def _restore(inverses: list["Command"]) -> "Command":
    return inverses[0] if len(inverses) == 1 else Batch(commands=inverses)


# --------------------------------------------------------------------------- base


class BaseCommand(CamelModel):
    model_config = ConfigDict(extra="forbid")

    def apply(self, project: Project) -> tuple[Project, "Command"]:
        """Pure: returns the edited copy and the command that undoes this one."""
        p = project.model_copy(deep=True)
        inverse = self._apply(p)
        return p, inverse

    @abstractmethod
    def _apply(self, p: Project) -> "Command":
        """Mutate the private copy ``p`` in place and return the inverse."""


# --------------------------------------------------------------------------- project


class RenameProject(BaseCommand):
    type: Literal["RenameProject"] = "RenameProject"
    name: str

    def _apply(self, p: Project) -> "Command":
        old, p.name = p.name, self.name
        return RenameProject(name=old)


class SetSettings(BaseCommand):
    type: Literal["SetSettings"] = "SetSettings"
    settings: ProjectSettings

    def _apply(self, p: Project) -> "Command":
        old, p.settings = p.settings, self.settings.model_copy(deep=True)
        return SetSettings(settings=old)


# --------------------------------------------------------------------------- assets


class AddAsset(BaseCommand):
    type: Literal["AddAsset"] = "AddAsset"
    asset: Asset
    index: int | None = None

    def _apply(self, p: Project) -> "Command":
        if p.asset(self.asset.id) is not None:
            raise CommandError(f"asset {self.asset.id} already exists")
        _put(p.assets, self.asset.model_copy(deep=True), self.index)
        return RemoveAsset(asset_id=self.asset.id)


class RemoveAsset(BaseCommand):
    """Remove an asset that nothing references any more."""

    type: Literal["RemoveAsset"] = "RemoveAsset"
    asset_id: str

    def _apply(self, p: Project) -> "Command":
        aid = self.asset_id
        refs = [t.asset_id for b in p.beats for t in b.takes]
        for b in p.beats:
            for c in b.cut:
                refs += [c.asset_id, c.angle_asset_id or ""]
                if c.audio.replacement is not None:
                    refs.append(c.audio.replacement.asset_id)
        refs += [o.asset_id for o in p.overlays]
        refs += [m.asset_id for g in p.sync_groups for m in g.members]
        refs += [m.target.asset_id for m in p.markers if isinstance(m.target, AssetMarkerTarget)]
        refs += [e.asset_id for e in p.overrides.transcript_edits]
        if aid in refs:
            raise CommandError(f"asset {aid} is still referenced")
        old, i = _pop(p.assets, aid, "asset")
        return AddAsset(asset=old, index=i)


class RelinkAsset(BaseCommand):
    type: Literal["RelinkAsset"] = "RelinkAsset"
    asset_id: str
    path: str
    rel_path: str | None = None

    def _apply(self, p: Project) -> "Command":
        asset = _asset(p, self.asset_id)
        inverse = RelinkAsset(asset_id=asset.id, path=asset.path, rel_path=asset.rel_path)
        asset.path, asset.rel_path = self.path, self.rel_path
        return inverse


class PutSyncGroup(BaseCommand):
    type: Literal["PutSyncGroup"] = "PutSyncGroup"
    group: SyncGroup
    index: int | None = None

    def _apply(self, p: Project) -> "Command":
        for m in self.group.members:
            _asset(p, m.asset_id)
        others = {m.asset_id for g in p.sync_groups if g.id != self.group.id for m in g.members}
        clash = others & {m.asset_id for m in self.group.members}
        if clash:
            raise CommandError(f"assets already in another sync group: {sorted(clash)}")
        old, i = _put(p.sync_groups, self.group.model_copy(deep=True), self.index)
        if old is None:
            return RemoveSyncGroup(group_id=self.group.id)
        return PutSyncGroup(group=old, index=i)


class RemoveSyncGroup(BaseCommand):
    type: Literal["RemoveSyncGroup"] = "RemoveSyncGroup"
    group_id: str

    def _apply(self, p: Project) -> "Command":
        old, i = _pop(p.sync_groups, self.group_id, "sync group")
        return PutSyncGroup(group=old, index=i)


# --------------------------------------------------------------------------- beats


class AddBeat(BaseCommand):
    type: Literal["AddBeat"] = "AddBeat"
    beat: Beat
    index: int | None = None

    def _apply(self, p: Project) -> "Command":
        if p.beat(self.beat.id) is not None:
            raise CommandError(f"beat {self.beat.id} already exists")
        clash = _all_item_ids(p) & {c.id for c in self.beat.cut}
        if clash:
            raise CommandError(f"clip item ids already used: {sorted(clash)}")
        _put(p.beats, self.beat.model_copy(deep=True), self.index)
        return RemoveBeat(beat_id=self.beat.id)


class RemoveBeat(BaseCommand):
    """Remove a beat (merge/split plumbing). Excluding a beat is ``SetBeatIncluded``."""

    type: Literal["RemoveBeat"] = "RemoveBeat"
    beat_id: str

    def _apply(self, p: Project) -> "Command":
        anchored = [
            o.id
            for o in p.overlays
            if isinstance(o.anchor, BeatAnchor) and o.anchor.beat_id == self.beat_id
        ]
        if anchored:
            raise CommandError(f"overlays anchored to beat {self.beat_id}: {anchored}")
        old, i = _pop(p.beats, self.beat_id, "beat")
        return AddBeat(beat=old, index=i)


class PutBeat(BaseCommand):
    """Replace an existing beat by id with the given content (restore primitive)."""

    type: Literal["PutBeat"] = "PutBeat"
    beat: Beat

    def _apply(self, p: Project) -> "Command":
        i = _index(p.beats, self.beat.id, "beat")
        others = {c.id for b in p.beats if b.id != self.beat.id for c in b.cut}
        clash = others & {c.id for c in self.beat.cut}
        if clash:
            raise CommandError(f"clip item ids already used: {sorted(clash)}")
        old = p.beats[i]
        p.beats[i] = self.beat.model_copy(deep=True)
        return PutBeat(beat=old)


class MoveBeat(BaseCommand):
    """Reorder: move a beat to ``to_index`` (story order). Transitions may go dormant."""

    type: Literal["MoveBeat"] = "MoveBeat"
    beat_id: str
    to_index: int = Field(ge=0)

    def _apply(self, p: Project) -> "Command":
        beat, i = _pop(p.beats, self.beat_id, "beat")
        p.beats.insert(min(self.to_index, len(p.beats)), beat)
        return MoveBeat(beat_id=self.beat_id, to_index=i)


class UpdateBeat(BaseCommand):
    """Edit beat metadata. Fields left unset are unchanged; locks unless ``locked`` given."""

    type: Literal["UpdateBeat"] = "UpdateBeat"
    beat_id: str
    label: str | None = None
    summary: str | None = None
    role: BeatRole | None = None
    locked: bool | None = None

    def _apply(self, p: Project) -> "Command":
        beat = _beat(p, self.beat_id)
        inverse = _snapshot(beat)
        fields = ("label", "summary", "role", "locked")
        changes = {k: getattr(self, k) for k in fields if k in self.model_fields_set}
        for key in ("label", "role", "locked"):
            if key in changes and changes[key] is None:
                raise CommandError(f"{key} cannot be null")
        changes.setdefault("locked", True)
        for key, value in changes.items():
            setattr(beat, key, value)
        return inverse


class SetBeatIncluded(BaseCommand):
    type: Literal["SetBeatIncluded"] = "SetBeatIncluded"
    beat_id: str
    included: bool

    def _apply(self, p: Project) -> "Command":
        beat = _beat(p, self.beat_id)
        inverse = _snapshot(beat)
        beat.included = self.included
        beat.locked = True
        return inverse


# --------------------------------------------------------------------------- takes


class SetTakeStatus(BaseCommand):
    """Mark a take alternate or rejected. Selecting a take is ``PromoteTake``."""

    type: Literal["SetTakeStatus"] = "SetTakeStatus"
    beat_id: str
    segment_id: str
    status: Literal["alternate", "rejected"]

    def _apply(self, p: Project) -> "Command":
        beat = _beat(p, self.beat_id)
        take = beat.take(self.segment_id)
        if take is None:
            raise CommandError(f"unknown take {self.segment_id} in beat {beat.id}")
        inverse = _snapshot(beat)
        take.status = self.status
        beat.locked = True
        return inverse


class MoveTake(BaseCommand):
    """Move a take to another beat (it arrives as an alternate). Locks both beats."""

    type: Literal["MoveTake"] = "MoveTake"
    segment_id: str
    from_beat_id: str
    to_beat_id: str
    index: int | None = None

    def _apply(self, p: Project) -> "Command":
        if self.from_beat_id == self.to_beat_id:
            raise CommandError("source and target beats are the same")
        src, dst = _beat(p, self.from_beat_id), _beat(p, self.to_beat_id)
        take = src.take(self.segment_id)
        if take is None:
            raise CommandError(f"unknown take {self.segment_id} in beat {src.id}")
        if dst.take(self.segment_id) is not None:
            raise CommandError(f"take {self.segment_id} already in beat {dst.id}")
        inverse = Batch(commands=[_snapshot(src), _snapshot(dst)])
        src.takes.remove(take)
        if take.status == "selected":
            take.status = "alternate"
        pos = len(dst.takes) if self.index is None else max(0, min(self.index, len(dst.takes)))
        dst.takes.insert(pos, take)
        src.locked = dst.locked = True
        return inverse


class PromoteTake(BaseCommand):
    """Make a take the selected one and rebuild the beat's cut from it.

    The new cut item gets ``new_item_id``, the take range plus the project clip padding
    (trims reset), and the audio settings of the previous first cut item. Transitions on
    the beat's outer edges are re-attached to the new item; transitions inside the old
    cut are left dormant.
    """

    type: Literal["PromoteTake"] = "PromoteTake"
    beat_id: str
    segment_id: str
    new_item_id: str = Field(default_factory=lambda: ids.new_id(ids.CLIP))

    def _apply(self, p: Project) -> "Command":
        beat = _beat(p, self.beat_id)
        take = beat.take(self.segment_id)
        if take is None:
            raise CommandError(f"unknown take {self.segment_id} in beat {beat.id}")
        if self.new_item_id in _all_item_ids(p):
            raise CommandError(f"clip item id {self.new_item_id} already used")
        asset = _asset(p, take.asset_id)
        pad = p.settings.clip_padding
        source_in = max(0, take.range.start_us - pad.before_us)
        source_out = min(asset.probe.duration_us, take.range.end_us + pad.after_us)
        if source_out <= source_in:
            raise CommandError(f"take {take.segment_id} has an empty range")

        inverses: list[Command] = [_snapshot(beat)]
        audio = beat.cut[0].audio.model_copy(deep=True) if beat.cut else ClipAudio()
        first_old = beat.cut[0].id if beat.cut else None
        last_old = beat.cut[-1].id if beat.cut else None
        for t in p.transitions:
            hit_after = last_old is not None and t.after_item_id == last_old
            hit_before = first_old is not None and t.before_item_id == first_old
            if hit_after or hit_before:
                inverses.append(PutTransition(transition=t.model_copy(deep=True)))
                if hit_after:
                    t.after_item_id = self.new_item_id
                if hit_before:
                    t.before_item_id = self.new_item_id

        for other in beat.takes:
            if other.status == "selected":
                other.status = "alternate"
        take.status = "selected"
        beat.cut = [
            ClipItem(
                id=self.new_item_id,
                asset_id=take.asset_id,
                segment_id=take.segment_id,
                source_in_us=source_in,
                source_out_us=source_out,
                audio=audio,
            )
        ]
        beat.locked = True
        return _restore(inverses)


# --------------------------------------------------------------------------- clip items


class TrimItem(BaseCommand):
    type: Literal["TrimItem"] = "TrimItem"
    item_id: str
    source_in_us: NonNegativeMicros
    source_out_us: NonNegativeMicros

    def _apply(self, p: Project) -> "Command":
        beat, _, item = _item(p, self.item_id)
        _check_source_range(p, item.asset_id, self.source_in_us, self.source_out_us)
        inverse = _snapshot(beat)
        item.source_in_us, item.source_out_us = self.source_in_us, self.source_out_us
        beat.locked = True
        return inverse


class BladeItem(BaseCommand):
    """Split an item at source time ``at_us``.

    The left part keeps the id, the right part gets ``new_item_id``; a transition on the
    cut after the original item moves to the right part, and item markers at or after
    the split move with it. Fade-out goes to the right part, fade-in stays on the left.
    """

    type: Literal["BladeItem"] = "BladeItem"
    item_id: str
    at_us: Micros
    new_item_id: str = Field(default_factory=lambda: ids.new_id(ids.CLIP))

    def _apply(self, p: Project) -> "Command":
        beat, i, item = _item(p, self.item_id)
        if not item.source_in_us < self.at_us < item.source_out_us:
            raise CommandError(f"blade point {self.at_us} outside item {item.id}")
        if self.new_item_id in _all_item_ids(p):
            raise CommandError(f"clip item id {self.new_item_id} already used")
        inverses: list[Command] = [_snapshot(beat)]

        right = item.model_copy(deep=True)
        right.id = self.new_item_id
        right.source_in_us = self.at_us
        right.audio.fade_in_us = 0
        if right.audio.replacement is not None:
            right.audio.replacement.source_in_us += self.at_us - item.source_in_us
        item.source_out_us = self.at_us
        item.audio.fade_out_us = 0
        beat.cut.insert(i + 1, right)
        beat.locked = True

        for t in p.transitions:
            if t.after_item_id == item.id:
                inverses.append(PutTransition(transition=t.model_copy(deep=True)))
                t.after_item_id = right.id
        for m in p.markers:
            if (
                isinstance(m.target, ItemMarkerTarget)
                and m.target.item_id == item.id
                and m.time_us >= self.at_us
            ):
                inverses.append(PutMarker(marker=m.model_copy(deep=True)))
                m.target = ItemMarkerTarget(item_id=right.id)
        return _restore(inverses)


class SetItemEnabled(BaseCommand):
    """``enabled=False`` is ripple delete: the item leaves the main line, gap closed."""

    type: Literal["SetItemEnabled"] = "SetItemEnabled"
    item_id: str
    enabled: bool

    def _apply(self, p: Project) -> "Command":
        beat, _, item = _item(p, self.item_id)
        inverse = _snapshot(beat)
        item.enabled = self.enabled
        beat.locked = True
        return inverse


class SetClipAudio(BaseCommand):
    type: Literal["SetClipAudio"] = "SetClipAudio"
    item_id: str
    audio: ClipAudio

    def _apply(self, p: Project) -> "Command":
        beat, _, item = _item(p, self.item_id)
        if self.audio.replacement is not None:
            _asset(p, self.audio.replacement.asset_id)
        inverse = _snapshot(beat)
        item.audio = self.audio.model_copy(deep=True)
        beat.locked = True
        return inverse


# --------------------------------------------------------------------------- transitions


class SetTransition(BaseCommand):
    """Put a transition on an active main-line cut (replaces the one on that cut)."""

    type: Literal["SetTransition"] = "SetTransition"
    transition: Transition

    def _apply(self, p: Project) -> "Command":
        t = self.transition
        if not p.is_transition_active(t):
            raise CommandError(
                f"items {t.after_item_id} and {t.before_item_id} are not adjacent on the main line"
            )
        if t.duration_us <= 0:
            raise CommandError("transition duration must be positive")
        clash = [x for x in p.transitions if x.id == t.id and x.after_item_id != t.after_item_id]
        if clash:
            raise CommandError(f"transition id {t.id} already used on another cut")
        existing = [
            (i, x) for i, x in enumerate(p.transitions) if x.after_item_id == t.after_item_id
        ]
        if not existing:
            p.transitions.append(t.model_copy(deep=True))
            return RemoveTransition(transition_id=t.id)
        i, old = existing[0]
        p.transitions[i] = t.model_copy(deep=True)
        if old.id == t.id:
            return PutTransition(transition=old)
        return Batch(
            commands=[RemoveTransition(transition_id=t.id), PutTransition(transition=old, index=i)]
        )


class PutTransition(BaseCommand):
    """Restore primitive: upsert a transition by id without adjacency checks."""

    type: Literal["PutTransition"] = "PutTransition"
    transition: Transition
    index: int | None = None

    def _apply(self, p: Project) -> "Command":
        t = self.transition
        if any(x.after_item_id == t.after_item_id and x.id != t.id for x in p.transitions):
            raise CommandError(f"another transition already sits after {t.after_item_id}")
        old, i = _put(p.transitions, t.model_copy(deep=True), self.index)
        if old is None:
            return RemoveTransition(transition_id=t.id)
        return PutTransition(transition=old, index=i)


class RemoveTransition(BaseCommand):
    type: Literal["RemoveTransition"] = "RemoveTransition"
    transition_id: str

    def _apply(self, p: Project) -> "Command":
        old, i = _pop(p.transitions, self.transition_id, "transition")
        return PutTransition(transition=old, index=i)


# --------------------------------------------------------------------------- overlays


class PutOverlay(BaseCommand):
    type: Literal["PutOverlay"] = "PutOverlay"
    overlay: OverlayItem
    index: int | None = None

    def _apply(self, p: Project) -> "Command":
        o = self.overlay
        _check_source_range(p, o.asset_id, o.source_in_us, o.source_out_us)
        if isinstance(o.anchor, BeatAnchor):
            _beat(p, o.anchor.beat_id)
        old, i = _put(p.overlays, o.model_copy(deep=True), self.index)
        if old is None:
            return RemoveOverlay(overlay_id=o.id)
        return PutOverlay(overlay=old, index=i)


class RemoveOverlay(BaseCommand):
    type: Literal["RemoveOverlay"] = "RemoveOverlay"
    overlay_id: str

    def _apply(self, p: Project) -> "Command":
        old, i = _pop(p.overlays, self.overlay_id, "overlay")
        return PutOverlay(overlay=old, index=i)


# --------------------------------------------------------------------------- constraints


class PutConstraint(BaseCommand):
    type: Literal["PutConstraint"] = "PutConstraint"
    constraint: GroupingConstraint
    index: int | None = None

    def _apply(self, p: Project) -> "Command":
        if self.constraint.a == self.constraint.b:
            raise CommandError("a constraint needs two different segments")
        old, i = _put(p.constraints, self.constraint.model_copy(deep=True), self.index)
        if old is None:
            return RemoveConstraint(constraint_id=self.constraint.id)
        return PutConstraint(constraint=old, index=i)


class RemoveConstraint(BaseCommand):
    type: Literal["RemoveConstraint"] = "RemoveConstraint"
    constraint_id: str

    def _apply(self, p: Project) -> "Command":
        old, i = _pop(p.constraints, self.constraint_id, "constraint")
        return PutConstraint(constraint=old, index=i)


# --------------------------------------------------------------------------- markers


class PutMarker(BaseCommand):
    type: Literal["PutMarker"] = "PutMarker"
    marker: Marker
    index: int | None = None

    def _apply(self, p: Project) -> "Command":
        old, i = _put(p.markers, self.marker.model_copy(deep=True), self.index)
        if old is None:
            return RemoveMarker(marker_id=self.marker.id)
        return PutMarker(marker=old, index=i)


class RemoveMarker(BaseCommand):
    type: Literal["RemoveMarker"] = "RemoveMarker"
    marker_id: str

    def _apply(self, p: Project) -> "Command":
        old, i = _pop(p.markers, self.marker_id, "marker")
        return PutMarker(marker=old, index=i)


# --------------------------------------------------------------------------- overrides


class PutTranscriptEdit(BaseCommand):
    type: Literal["PutTranscriptEdit"] = "PutTranscriptEdit"
    edit: TranscriptEdit
    index: int | None = None

    def _apply(self, p: Project) -> "Command":
        _asset(p, self.edit.asset_id)
        edits = p.overrides.transcript_edits
        old, i = _put(edits, self.edit.model_copy(deep=True), self.index)
        if old is None:
            return RemoveTranscriptEdit(edit_id=self.edit.id)
        return PutTranscriptEdit(edit=old, index=i)


class RemoveTranscriptEdit(BaseCommand):
    type: Literal["RemoveTranscriptEdit"] = "RemoveTranscriptEdit"
    edit_id: str

    def _apply(self, p: Project) -> "Command":
        old, i = _pop(p.overrides.transcript_edits, self.edit_id, "transcript edit")
        return PutTranscriptEdit(edit=old, index=i)


class SetSegmentDismissed(BaseCommand):
    """Dismiss (or restore) an orphan segment."""

    type: Literal["SetSegmentDismissed"] = "SetSegmentDismissed"
    segment_id: str
    dismissed: bool
    index: int | None = None

    def _apply(self, p: Project) -> "Command":
        ids_ = p.overrides.dismissed_segment_ids
        if self.segment_id in ids_:
            i = ids_.index(self.segment_id)
            if self.dismissed:
                return SetSegmentDismissed(segment_id=self.segment_id, dismissed=True)
            ids_.pop(i)
            return SetSegmentDismissed(segment_id=self.segment_id, dismissed=True, index=i)
        if not self.dismissed:
            return SetSegmentDismissed(segment_id=self.segment_id, dismissed=False)
        pos = len(ids_) if self.index is None else max(0, min(self.index, len(ids_)))
        ids_.insert(pos, self.segment_id)
        return SetSegmentDismissed(segment_id=self.segment_id, dismissed=False)


# --------------------------------------------------------------------------- batch


class SetEditor(BaseCommand):
    """Replace an interactive gesture atomically; None restores legacy edit ownership."""

    type: Literal["SetEditor"] = "SetEditor"
    document: EditorDocument | None

    def _apply(self, p: Project) -> "Command":
        from videoflow.editor.resolve import document_for, validate_assets

        previous = document_for(p)
        if self.document is not None:
            validate_assets(self.document, p)
        if p.__pydantic_extra__ is None:
            p.__pydantic_extra__ = {}
        if self.document is None:
            p.__pydantic_extra__.pop("editor", None)
        else:
            p.__pydantic_extra__["editor"] = self.document.dump()
        return SetEditor(document=previous)


class Batch(BaseCommand):
    """Several commands applied in order as one; its inverse undoes them in reverse."""

    type: Literal["Batch"] = "Batch"
    commands: list["Command"]

    def _apply(self, p: Project) -> "Command":
        raise NotImplementedError  # apply() is overridden

    def apply(self, project: Project) -> tuple[Project, "Command"]:
        inverses: list[Command] = []
        for cmd in self.commands:
            project, inv = cmd.apply(project)
            inverses.append(inv)
        if not self.commands:
            project = project.model_copy(deep=True)
        inverses.reverse()
        return project, Batch(commands=inverses)


type Command = Annotated[
    RenameProject
    | SetSettings
    | AddAsset
    | RemoveAsset
    | RelinkAsset
    | PutSyncGroup
    | RemoveSyncGroup
    | AddBeat
    | RemoveBeat
    | PutBeat
    | MoveBeat
    | UpdateBeat
    | SetBeatIncluded
    | SetTakeStatus
    | MoveTake
    | PromoteTake
    | TrimItem
    | BladeItem
    | SetItemEnabled
    | SetClipAudio
    | SetTransition
    | PutTransition
    | RemoveTransition
    | PutOverlay
    | RemoveOverlay
    | PutConstraint
    | RemoveConstraint
    | PutMarker
    | RemoveMarker
    | PutTranscriptEdit
    | RemoveTranscriptEdit
    | SetSegmentDismissed
    | SetEditor
    | Batch,
    Field(discriminator="type"),
]

Batch.model_rebuild()

COMMAND_TYPES: tuple[type[BaseCommand], ...] = tuple(BaseCommand.__subclasses__())

command_adapter: TypeAdapter[Command] = TypeAdapter(Command)
command_list_adapter: TypeAdapter[list[Command]] = TypeAdapter(list[Command])


def parse_command(data: object) -> Command:
    return command_adapter.validate_python(data)


def apply_batch(project: Project, commands: list[Command]) -> tuple[Project, list[Command]]:
    """Apply commands in order as one revision.

    Returns the new project (``revision + 1``) and the inverses in undo order: applying
    them as a batch restores the input project (with a new revision). All or nothing:
    a failing command raises :class:`CommandError` and the input is untouched.
    """
    current = project
    inverses: list[Command] = []
    for cmd in commands:
        current, inv = cmd.apply(current)
        inverses.append(inv)
    inverses.reverse()
    if current is project:
        current = project.model_copy(deep=True)
    current.revision = project.revision + 1
    return current, inverses
