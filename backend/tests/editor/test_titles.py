import numpy as np
import pytest
from pydantic import ValidationError

from tests.timeline.builders import ProjectBuilder, S
from videoflow.editor.models import EditorClip, EditorDocument, Title
from videoflow.editor.titles import (
    DETAIL_SIZE,
    LOWER_THIRD_BOTTOM,
    LOWER_THIRD_LEFT,
    PAD_X,
    layout_title,
    title_image,
)
from videoflow.editor.transitions import plan_transitions
from videoflow.exporters.otio_compile import compile_timeline
from videoflow.project.commands import SetEditor
from videoflow.timeline.resolve import resolve


def text(title: Title | None = None, **values) -> EditorClip:
    data = (
        dict(id="t", kind="text", name="Title", start=0, source_in=0, source_out=50, layer=1)
        | values
    )
    return EditorClip(title=title or Title(text="Hello"), **data)


def test_title_picture_is_transparent_around_text_and_boxes():
    plain = title_image(Title(text="Hello", size=0.2), 320, 180)
    alpha = plain.getchannel("A")
    assert alpha.getpixel((5, 5)) == 0 and alpha.getbbox() is not None
    left, top, right, bottom = alpha.getbbox()
    assert abs((left + right) / 2 - 160) < 6 and abs((top + bottom) / 2 - 90) < 12
    pixels = np.asarray(plain)
    white = (pixels[..., 3] == 255) & (pixels[..., :3].min(axis=2) == 255)
    shadow = (pixels[..., 3] > 0) & (pixels[..., 3] < 200) & (pixels[..., :3].max(axis=2) == 0)
    assert white.any() and shadow.any()  # white text over a soft black shadow
    boxed = title_image(
        Title(
            text="Name",
            style="lower_third",
            size=0.1,
            box=True,
            box_color="#ff0000",
            box_opacity=0.5,
        ),
        320,
        180,
    )
    layout = layout_title(Title(text="Name", style="lower_third", size=0.1, box=True), 320, 180)
    left, top, right, bottom = (round(v) for v in layout.bounds)
    assert boxed.getpixel((left + 1, top + 1)) == (255, 0, 0, 128)
    assert boxed.getpixel((left - 2, top + 1))[3] == 0
    assert boxed.getchannel("A").getbbox() == (left, top, right, bottom)


def test_text_clips_have_a_title_and_no_media():
    assert text().kind == "text"
    with pytest.raises(ValidationError):
        EditorClip(id="t", kind="text", name="T", start=0, source_in=0, source_out=5)
    with pytest.raises(ValidationError):
        text(asset_id="a")
    with pytest.raises(ValidationError):
        text(speed=2)
    with pytest.raises(ValidationError):
        Title(text=" \n ")
    with pytest.raises(ValidationError):
        EditorClip(
            id="v",
            kind="video",
            asset_id="a",
            name="V",
            start=0,
            source_in=0,
            source_out=5,
            title=Title(text="x"),
        )


def test_title_is_centred_and_lines_stack():
    layout = layout_title(Title(text="Big title\nsecond line", size=0.1), 1920, 1080)
    first, second = layout.lines
    assert layout.centred and first.bold and second.bold and first.size == second.size == 108
    for line in layout.lines:
        assert line.left + line.width / 2 == pytest.approx(960)
    left, top, right, bottom = layout.bounds
    assert (top + bottom) / 2 == pytest.approx(540)
    assert second.top == pytest.approx(first.top + first.height)


def test_lower_third_sits_bottom_left_with_a_smaller_detail_line():
    title = Title(text="Ada Lovelace\nMathematician", style="lower_third", size=0.06, box=True)
    layout = layout_title(title, 1920, 1080)
    name, role = layout.lines
    assert not layout.centred and name.bold and not role.bold
    assert role.size == pytest.approx(name.size * DETAIL_SIZE)
    left, top, right, bottom = layout.bounds
    assert left == pytest.approx(LOWER_THIRD_LEFT * 1920)
    assert bottom == pytest.approx(LOWER_THIRD_BOTTOM * 1080)
    assert name.left == role.left == pytest.approx(left + PAD_X * name.size)
    assert role.top > name.top + name.height


def test_text_clips_fade_and_resolve_as_titled_gaps_on_video_tracks():
    project = ProjectBuilder().asset("a", 10 * S).build()
    video = EditorClip(
        id="v", kind="video", asset_id="a", name="Take", start=0, source_in=0, source_out=50
    )
    doc = EditorDocument(clips=[video, text(fade_in=10, fade_out=5)])
    plan = plan_transitions(doc, lambda c: 250)
    assert plan.video_fade_in["t"] == 10 and plan.video_fade_out["t"] == 5
    updated, _ = SetEditor(document=doc).apply(project)
    timeline = resolve(updated)
    assert [t.id for t in timeline.tracks if t.kind == "video"] == ["V1", "V2"]
    titled = timeline.track("V2").clips[0]
    assert titled.asset_id == "__gap__" and titled.dump()["title"]["text"] == "Hello"
    assert not any(
        t.clips and t.id.startswith("A") and t.clips[0].item_id == "t" for t in timeline.tracks
    )
    assert "editor_titles" in {w.code for w in timeline.warnings}
    otio = compile_timeline(timeline, updated)
    assert otio.duration().value == 50
