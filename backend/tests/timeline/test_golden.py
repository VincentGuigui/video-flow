"""Golden files: resolved timelines of fixed projects.

Regenerate after an intended change with ``VIDEOFLOW_UPDATE_GOLDEN=1 uv run pytest
tests/timeline/test_golden.py`` and review the diff.
"""

import json
import os
from collections.abc import Callable
from pathlib import Path

import pytest

from tests.project.conftest import load_fixture_dict
from tests.timeline.builders import (
    ProjectBuilder,
    S,
    beat_overlay,
    clip,
    project_overlay,
    transition,
)
from videoflow.core.time import Rational
from videoflow.project.models import Project
from videoflow.timeline.resolve import resolve
from videoflow.timeline.validate import invariant_violations

GOLDEN = Path(__file__).resolve().parent / "golden"


def full_fixture() -> Project:
    return Project.model_validate(load_fixture_dict())


def alignments() -> Project:
    """30 fps, one transition per alignment, odd centered duration."""
    b = ProjectBuilder()
    b.asset("ast_a", 60 * S).asset("ast_b", 60 * S)
    b.beat("beat_1", clip("clip_a", "ast_a", 10 * S, 14 * S))
    b.beat("beat_2", clip("clip_b", "ast_b", 5 * S, 9 * S))
    b.beat("beat_3", clip("clip_c", "ast_a", 20 * S, 23 * S))
    b.beat("beat_4", clip("clip_d", "ast_b", 30 * S, 34 * S))
    b.transitions += [
        transition("tr_center", "clip_a", "clip_b", 500_000, "center"),
        transition("tr_start", "clip_b", "clip_c", 400_000, "start", "wipe_left"),
        transition("tr_end", "clip_c", "clip_d", 400_000, "end", "dip_black"),
    ]
    return b.build()


def ntsc_ripple() -> Project:
    """29.97 fps: disabled item, excluded beat, dormant transition, clamped overlays."""
    b = ProjectBuilder(rate=Rational.of(30000, 1001))
    b.asset("ast_a", 120 * S).asset("ast_broll", 30 * S)
    b.beat("beat_1", clip("clip_1", "ast_a", 1_234_567, 5_432_100))
    b.beat(
        "beat_2",
        clip("clip_2a", "ast_a", 10 * S, 12_500_000),
        clip("clip_2b", "ast_a", 12_500_000, 14 * S),
        clip("clip_2c", "ast_a", 14 * S, 17_333_333),
    )
    b.beat("beat_3", clip("clip_3", "ast_a", 40 * S, 44 * S), included=False)
    b.beat("beat_4", clip("clip_4", "ast_a", 60 * S, 63_100_000))
    b.beats[1].cut[1].enabled = False
    b.transitions += [
        transition("tr_1", "clip_1", "clip_2a", 333_333),
        transition("tr_2", "clip_2c", "clip_3", 500_000),
        transition("tr_3", "clip_2a", "clip_2b", 500_000),
    ]
    b.overlays += [
        beat_overlay("ovl_neg", "ast_broll", "beat_1", -2 * S, 3 * S),
        beat_overlay("ovl_beat2", "ast_broll", "beat_2", 1 * S, 2 * S),
        beat_overlay("ovl_tail", "ast_broll", "beat_4", 2 * S, 5 * S),
        beat_overlay("ovl_excluded", "ast_broll", "beat_3", 0, 1 * S),
        project_overlay("ovl_far", "ast_broll", 600 * S, 1 * S),
    ]
    return b.build()


def short_handles() -> Project:
    """25 fps: clips at the very start / end of their media need freeze frames."""
    b = ProjectBuilder(rate=Rational.of(25))
    b.asset("ast_a", 8 * S).asset("ast_b", 8 * S)
    b.beat("beat_1", clip("clip_a", "ast_a", 4 * S, 7_900_000))
    b.beat("beat_2", clip("clip_b", "ast_b", 0, 3 * S))
    b.beat("beat_3", clip("clip_c", "ast_a", 200_000, 600_000))
    b.transitions += [
        transition("tr_ab", "clip_a", "clip_b", 1 * S, "center"),
        transition("tr_bc", "clip_b", "clip_c", 2 * S, "end"),
    ]
    return b.build()


SCENARIOS: dict[str, Callable[[], Project]] = {
    "full_fixture": full_fixture,
    "alignments_30": alignments,
    "ntsc_ripple": ntsc_ripple,
    "short_handles_25": short_handles,
}


def _text(project: Project) -> str:
    return json.dumps(resolve(project).dump(), indent=2, ensure_ascii=False) + "\n"


@pytest.mark.parametrize("name", sorted(SCENARIOS))
def test_golden(name: str) -> None:
    project = SCENARIOS[name]()
    timeline = resolve(project)
    assert invariant_violations(timeline) == []
    text = _text(project)
    path = GOLDEN / f"{name}.resolved.json"
    if os.environ.get("VIDEOFLOW_UPDATE_GOLDEN") == "1":
        path.write_text(text, encoding="utf-8", newline="\n")
    assert path.exists(), f"missing golden {path.name}: set VIDEOFLOW_UPDATE_GOLDEN=1"
    assert text == path.read_text(encoding="utf-8")
