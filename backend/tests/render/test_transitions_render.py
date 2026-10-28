import pytest

from tests.render import test_render as base
from videoflow.editor.models import EditorClip, EditorDocument, EditorTransition, Transform
from videoflow.media import ffmpeg
from videoflow.project.commands import SetEditor
from videoflow.render.runner import render_project

edit = base.edit  # shared fixture
pixels = base.pixels


def cut(bundle, kind: str) -> None:
    red, blue = (a.id for a in bundle.project.assets)
    doc = EditorDocument(
        clips=[
            EditorClip(
                id="red",
                kind="video",
                asset_id=red,
                name="Red",
                start=0,
                source_in=10,
                source_out=35,
                link_id="p",
                transform=Transform(width=160, height=90),
            ),
            EditorClip(
                id="redaudio",
                kind="audio",
                asset_id=red,
                name="Red audio",
                start=0,
                source_in=10,
                source_out=35,
                link_id="p",
            ),
            EditorClip(
                id="blue",
                kind="video",
                asset_id=blue,
                name="Blue",
                start=25,
                source_in=10,
                source_out=35,
                transform=Transform(width=160, height=90),
            ),
        ],
        transitions=[
            EditorTransition(id="t", left_id="red", right_id="blue", type=kind, duration=10)
        ],
    )
    project, _ = SetEditor(document=doc).apply(bundle.project)
    bundle.save(project)


@pytest.mark.parametrize("kind", ["dissolve", "dip_black", "dip_white"])
async def test_transition_renders_at_the_cut_with_exact_frames(edit, tmp_path, kind):
    cut(edit, kind)
    output = await render_project(edit.project, edit, hw="cpu", normalize=False)
    probe = await ffmpeg.probe(output.path)
    assert probe.video.nb_frames == 50
    before = (await pixels(output.path, 15, tmp_path)).reshape(-1, 3).mean(axis=0)
    middle = (await pixels(output.path, 25, tmp_path)).reshape(-1, 3).mean(axis=0)
    after = (await pixels(output.path, 35, tmp_path)).reshape(-1, 3).mean(axis=0)
    assert before[0] > 200 and before[2] < 60
    assert after[2] > 200 and after[0] < 60
    if kind == "dissolve":
        assert 80 < middle[0] < 180 and 80 < middle[2] < 180
    elif kind == "dip_black":
        assert middle.max() < 40
    else:
        assert middle.min() > 215


async def test_edge_fades_render_from_and_to_black(edit, tmp_path):
    red = edit.project.assets[0].id
    doc = EditorDocument(
        clips=[
            EditorClip(
                id="red",
                kind="video",
                asset_id=red,
                name="Red",
                start=0,
                source_in=0,
                source_out=50,
                fade_in=10,
                fade_out=10,
                transform=Transform(width=160, height=90),
            ),
        ]
    )
    project, _ = SetEditor(document=doc).apply(edit.project)
    edit.save(project)
    output = await render_project(edit.project, edit, hw="cpu", normalize=False)
    red_level = [
        (await pixels(output.path, f, tmp_path)).reshape(-1, 3).mean(axis=0)[0]
        for f in (0, 5, 25, 45, 49)
    ]
    assert red_level[0] < 40 and 90 < red_level[1] < 170 and red_level[2] > 220
    assert 60 < red_level[3] < 170 and red_level[4] < 60
