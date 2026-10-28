import pytest

from videoflow.editor.models import EditorClip, VolumeRange
from videoflow.editor.volume import envelope, range_factor, volume_expression

MUTE = VolumeRange(start=20, end=30, ramp=4)
DUCK = VolumeRange(start=0, end=10, gain_db=-20, ramp=0, kind="duck")


def test_range_factor_ramps_outside_the_range():
    assert range_factor(MUTE, 15) == 1 and range_factor(MUTE, 34) == 1
    assert range_factor(MUTE, 18) == pytest.approx(0.5)
    assert range_factor(MUTE, 20) == 0 and range_factor(MUTE, 29) == 0
    assert range_factor(DUCK, 5) == pytest.approx(0.1)


def test_envelope_takes_the_lowest_range_and_expression_covers_the_clip():
    clip = EditorClip(
        id="a",
        kind="audio",
        asset_id="x",
        name="a",
        start=0,
        source_in=0,
        source_out=50,
        volume_ranges=[MUTE, DUCK],
    )
    assert envelope(clip, 25) == 0 and envelope(clip, 5) == pytest.approx(0.1)
    assert envelope(clip, 40) == 1
    expression = volume_expression(clip, 25)
    assert expression.startswith("min(") and "between(t,0.000000,0.400000)" in expression
    assert (
        volume_expression(clip.model_copy(update={"source_in": 40, "source_out": 90}), 25) is None
    )
