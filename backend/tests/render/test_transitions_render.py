import numpy as np
import pytest

from tests.render import test_render as base
from videoflow.editor.models import (
    EditorClip,
    EditorDocument,
    EditorTransition,
    Transform,
    VolumeRange,
    Zoom,
)
from videoflow.media import ffmpeg
from videoflow.media.ingest import ingest_files
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


@pytest.mark.parametrize("speed, frames", [(2.0, 25), (0.5, 100)])
async def test_clip_speed_renders_exact_length_with_audio(edit, tmp_path, speed, frames):
    red = edit.project.assets[0].id
    doc = EditorDocument(
        clips=[
            EditorClip(
                id="v",
                kind="video",
                asset_id=red,
                name="Red",
                start=0,
                source_in=0,
                source_out=50,
                link_id="p",
                speed=speed,
                transform=Transform(width=160, height=90),
            ),
            EditorClip(
                id="a",
                kind="audio",
                asset_id=red,
                name="Audio",
                start=0,
                source_in=0,
                source_out=50,
                link_id="p",
                speed=speed,
            ),
        ]
    )
    project, _ = SetEditor(document=doc).apply(edit.project)
    edit.save(project)
    output = await render_project(edit.project, edit, hw="cpu", normalize=False)
    probe = await ffmpeg.probe(output.path)
    assert probe.video.nb_frames == frames
    assert abs(probe.audio[0].duration_us - frames * 40_000) <= 40_000


def test_atempo_chain_stays_in_range():
    from videoflow.render.graph import _atempo

    assert _atempo(1) == ""
    assert _atempo(4) == "atempo=2,atempo=2,"
    assert _atempo(0.25) == "atempo=0.5,atempo=0.5,"


async def test_zoom_magnifies_toward_the_focus_point_and_returns(edit, tmp_path):
    quad = tmp_path / "quad.mp4"
    # Left half red, right half blue: zooming on the left edge fills the frame with red.
    made = await ffmpeg.run(
        [
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=red:s=80x90:r=25:d=3",
            "-f",
            "lavfi",
            "-i",
            "color=blue:s=80x90:r=25:d=3",
            "-filter_complex",
            "[0][1]hstack",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(quad),
        ]
    )
    assert made.ok, made.stderr_tail
    asset = (await ingest_files([quad])).assets[0]
    project = edit.project.model_copy(update={"assets": [*edit.project.assets, asset]})
    doc = EditorDocument(
        clips=[
            EditorClip(
                id="q",
                kind="video",
                asset_id=asset.id,
                name="Quad",
                start=0,
                source_in=0,
                source_out=50,
                transform=Transform(width=160, height=90),
                zooms=[Zoom(start=10, end=40, scale=4, x=0.0, y=0.5, ease_in=5, ease_out=5)],
            ),
        ]
    )
    project, _ = SetEditor(document=doc).apply(project)
    edit.save(project)
    output = await render_project(edit.project, edit, hw="cpu", normalize=False)
    assert (await ffmpeg.probe(output.path)).video.nb_frames == 50

    def right_quarter(picture):
        return picture[:, 120:].reshape(-1, 3).mean(axis=0)

    before = right_quarter(await pixels(output.path, 5, tmp_path))
    held = right_quarter(await pixels(output.path, 25, tmp_path))
    after = right_quarter(await pixels(output.path, 45, tmp_path))
    assert before[2] > 200 and after[2] > 200  # blue on the right without zoom
    assert held[0] > 200 and held[2] < 60  # zoomed on the left edge: red everywhere


async def test_mute_and_duck_ranges_shape_the_rendered_audio(edit, tmp_path):
    red = edit.project.assets[0].id
    doc = EditorDocument(
        clips=[
            EditorClip(
                id="a",
                kind="audio",
                asset_id=red,
                name="Tone",
                start=0,
                source_in=0,
                source_out=75,
                volume_ranges=[
                    VolumeRange(start=25, end=50, ramp=0),
                    VolumeRange(start=50, end=75, gain_db=-20, ramp=0, kind="duck"),
                ],
            ),
        ]
    )
    project, _ = SetEditor(document=doc).apply(edit.project)
    edit.save(project)
    output = await render_project(edit.project, edit, hw="cpu", normalize=False)
    pcm = tmp_path / "audio.f32"
    dumped = await ffmpeg.run(
        ["-y", "-i", str(output.path), "-vn", "-ac", "1", "-ar", "8000", "-f", "f32le", str(pcm)]
    )
    assert dumped.ok, dumped.stderr_tail
    samples = np.frombuffer(pcm.read_bytes(), dtype="<f4")

    def rms(a, b):
        part = samples[int(a * 8000) : int(b * 8000)]
        return float(np.sqrt(np.mean(part**2)))

    loud, muted, ducked = rms(0.1, 0.9), rms(1.1, 1.9), rms(2.1, 2.9)
    assert muted < loud * 0.01
    assert 0.07 < ducked / loud < 0.14  # -20 dB = 0.1
