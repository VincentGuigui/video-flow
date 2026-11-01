"""Keyframed transforms in the render (docs/features/keyframes.md)."""

from tests.render import test_render as base
from videoflow.editor.keyframes import piecewise, transform_at
from videoflow.editor.models import EditorClip, EditorDocument, Keyframe, Transform
from videoflow.project.commands import SetEditor
from videoflow.render.runner import render_project

edit = base.edit  # shared fixture: red.mp4 and blue.mp4, 160x90 at 25 fps
pixels = base.pixels
FULL = Transform(width=160, height=90)


def _over_red(bundle, **blue) -> None:
    red, blue_id = (a.id for a in bundle.project.assets)
    doc = EditorDocument(
        clips=[
            EditorClip(
                id="red", kind="video", asset_id=red, name="Red", start=0, source_in=0,
                source_out=50, transform=FULL,
            ),
            EditorClip(
                id="blue", kind="video", asset_id=blue_id, name="Blue", start=0, source_in=0,
                source_out=50, layer=1, **blue,
            ),
        ]
    )  # fmt: skip
    project, _ = SetEditor(document=doc).apply(bundle.project)
    bundle.save(project)


def _mean(picture, region=(slice(None), slice(None))):
    return picture[region].reshape(-1, 3).mean(axis=0)


def test_interpolation_holds_outside_and_eases_inside():
    keys = [
        Keyframe(frame=10, transform=Transform(x=0), ease="linear"),
        Keyframe(frame=20, transform=Transform(x=100)),
        Keyframe(frame=30, transform=Transform(x=0)),
    ]
    clip = EditorClip(
        id="v", kind="video", asset_id="a", name="v", start=0, source_in=0, source_out=40,
        keyframes=list(reversed(keys)),
    )  # fmt: skip
    assert [k.frame for k in clip.keyframes] == [10, 20, 30]  # sorted on load
    assert transform_at(clip, 0).x == 0 and transform_at(clip, 35).x == 0
    assert transform_at(clip, 15).x == 50  # linear
    assert transform_at(clip, 22.5).x == 100 - 100 * 0.15625  # smoothstep(0.25)
    expression = piecewise(clip.keyframes, lambda t: t.x, "s")
    assert expression.startswith("if(lt(s,10),0,if(lt(s,20),(0+100*")


async def test_opacity_keyframes_fade_the_picture(edit, tmp_path):
    keys = [
        Keyframe(frame=0, transform=FULL, ease="linear"),
        Keyframe(frame=20, transform=FULL.model_copy(update={"opacity": 0.0})),
    ]
    _over_red(edit, transform=FULL, keyframes=keys)
    output = await render_project(edit.project, edit, hw="cpu", normalize=False)
    start = _mean(await pixels(output.path, 0, tmp_path))
    middle = _mean(await pixels(output.path, 10, tmp_path))
    end = _mean(await pixels(output.path, 30, tmp_path))
    assert start[2] > 200 and start[0] < 60
    assert 90 < middle[0] < 170 and 90 < middle[2] < 170
    assert end[0] > 200 and end[2] < 60


async def test_animated_crop_reveals_what_lies_below(edit, tmp_path):
    keys = [
        Keyframe(frame=0, transform=FULL, ease="linear"),
        Keyframe(frame=20, transform=FULL.model_copy(update={"crop_left": 0.5})),
    ]
    _over_red(edit, transform=FULL, keyframes=keys)
    output = await render_project(edit.project, edit, hw="cpu", normalize=False)
    late = await pixels(output.path, 30, tmp_path)
    left, right = (
        _mean(late, (slice(None), slice(0, 70))),
        _mean(late, (slice(None), slice(90, None))),
    )
    assert left[0] > 200 and left[2] < 60  # cropped away: red shows
    assert right[2] > 200 and right[0] < 60  # the kept right half stays in place
    early = _mean(await pixels(output.path, 0, tmp_path), (slice(None), slice(0, 70)))
    assert early[2] > 200


async def test_rotation_turns_the_box_about_its_centre(edit, tmp_path):
    square = Transform(x=50, y=15, width=60, height=60, rotation=45)
    _over_red(edit, transform=square)
    output = await render_project(edit.project, edit, hw="cpu", normalize=False)
    frame = await pixels(output.path, 10, tmp_path)
    centre = _mean(frame, (slice(40, 50), slice(75, 85)))
    corner = _mean(frame, (slice(16, 20), slice(51, 55)))  # inside the unrotated box only
    beyond = _mean(frame, (slice(42, 48), slice(42, 46)))  # the diamond's left tip
    assert centre[2] > 200
    assert corner[0] > 200 and corner[2] < 60
    assert beyond[2] > 150
