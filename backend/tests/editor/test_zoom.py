import pytest

from videoflow.editor.models import EditorClip, Zoom
from videoflow.editor.zoom import factor, ramps, zoompan_expressions

Z = Zoom(start=10, end=40, scale=3, x=0.2, y=0.8, ease_in=10, ease_out=10)


def test_factor_eases_in_holds_and_eases_out():
    assert factor([Z], 9) == 1 and factor([Z], 40) == 1
    assert factor([Z], 15) == pytest.approx(2.0)  # half way through a smoothstep
    assert factor([Z], 25) == 3
    assert factor([Z], 35) == pytest.approx(2.0)


def test_ramps_shrink_to_fit_short_zooms():
    assert ramps(Zoom(start=0, end=10, ease_in=8, ease_out=8)) == (8, 2)


def test_zoompan_expressions_only_for_zooms_inside_the_clip():
    clip = EditorClip(
        id="c", kind="video", asset_id="a", name="c", start=0, source_in=0, source_out=50, zooms=[Z]
    )
    z, x, y = zoompan_expressions(clip)
    assert z.startswith("1+if(") and "0.2" in x and "0.8" in y
    outside = clip.model_copy(update={"source_in": 40, "source_out": 90})
    assert zoompan_expressions(outside) is None


def test_invalid_zoom_is_rejected():
    with pytest.raises(ValueError):
        Zoom(start=5, end=5)
