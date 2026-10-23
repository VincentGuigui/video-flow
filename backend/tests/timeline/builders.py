"""Deterministic project builders for resolver tests (readable ids, synthetic assets)."""

from dataclasses import dataclass, field

from videoflow.core.time import Rational
from videoflow.project.models import (
    Asset,
    AssetProbe,
    AudioStreamInfo,
    Beat,
    BeatAnchor,
    ClipItem,
    OverlayItem,
    Project,
    ProjectAnchor,
    ProjectSettings,
    Transition,
    VideoStreamInfo,
)

S = 1_000_000


def asset(asset_id: str, duration_us: int, rate: Rational | None = None) -> Asset:
    return Asset(
        id=asset_id,
        path=f"/media/{asset_id}.mp4",
        content_hash=f"xxh3:{asset_id}",
        probe=AssetProbe(
            duration_us=duration_us,
            video=VideoStreamInfo(width=1920, height=1080, frame_rate=rate or Rational.of(30)),
            audio_streams=[AudioStreamInfo(index=1, channels=2, sample_rate=48_000)],
        ),
    )


def clip(item_id: str, asset_id: str, source_in_us: int, source_out_us: int) -> ClipItem:
    return ClipItem(
        id=item_id, asset_id=asset_id, source_in_us=source_in_us, source_out_us=source_out_us
    )


def transition(
    tr_id: str,
    after: str,
    before: str,
    duration_us: int = 500_000,
    alignment: str = "center",
    type_: str = "dissolve",
) -> Transition:
    return Transition.model_validate(
        {
            "id": tr_id,
            "afterItemId": after,
            "beforeItemId": before,
            "type": type_,
            "durationUs": duration_us,
            "alignment": alignment,
        }
    )


def beat_overlay(
    ovl_id: str, asset_id: str, beat_id: str, offset_us: int, length_us: int
) -> OverlayItem:
    return OverlayItem(
        id=ovl_id,
        asset_id=asset_id,
        source_in_us=S,
        source_out_us=S + length_us,
        anchor=BeatAnchor(beat_id=beat_id, offset_us=offset_us),
    )


def project_overlay(ovl_id: str, asset_id: str, time_us: int, length_us: int) -> OverlayItem:
    return OverlayItem(
        id=ovl_id,
        asset_id=asset_id,
        source_in_us=S,
        source_out_us=S + length_us,
        anchor=ProjectAnchor(time_us=time_us),
    )


@dataclass
class ProjectBuilder:
    rate: Rational = field(default_factory=lambda: Rational.of(30))
    assets: list[Asset] = field(default_factory=list)
    beats: list[Beat] = field(default_factory=list)
    transitions: list[Transition] = field(default_factory=list)
    overlays: list[OverlayItem] = field(default_factory=list)

    def asset(self, asset_id: str, duration_us: int) -> "ProjectBuilder":
        self.assets.append(asset(asset_id, duration_us, self.rate))
        return self

    def beat(self, beat_id: str, *items: ClipItem, included: bool = True) -> "ProjectBuilder":
        self.beats.append(Beat(id=beat_id, label=beat_id, included=included, cut=list(items)))
        return self

    def build(self) -> Project:
        return Project(
            id="prj_test",
            name="test",
            revision=1,
            settings=ProjectSettings(frame_rate=self.rate),
            assets=self.assets,
            beats=self.beats,
            transitions=self.transitions,
            overlays=self.overlays,
        )
