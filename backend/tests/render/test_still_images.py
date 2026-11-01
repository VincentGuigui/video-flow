"""Still images: import, validation, render and exports (docs/features/still-images.md)."""

import asyncio
import json
import subprocess

import pytest

from tests.render import test_render as base
from videoflow.editor.models import EditorClip, EditorDocument, EditorTransition, Transform
from videoflow.editor.resolve import validate_assets
from videoflow.exporters.camtasia import export_camtasia
from videoflow.media import ffmpeg
from videoflow.media.caps import NO_WINDOW, locate_binaries
from videoflow.media.ingest import MEDIA_EXTENSIONS, ingest_files
from videoflow.project.commands import SetEditor
from videoflow.render.runner import render_project

edit = base.edit  # shared fixture: red.mp4 (with audio) and blue.mp4, 160x90 at 25 fps
pixels = base.pixels


async def _image(path, color, size="320x180") -> None:
    exe = locate_binaries().ffmpeg
    await asyncio.to_thread(
        subprocess.run,
        [str(exe), "-v", "error", "-y", "-f", "lavfi", "-i", f"color={color}:s={size}:d=1"]
        + ["-frames:v", "1", str(path)],
        check=True,
        capture_output=True,
        creationflags=NO_WINDOW,
    )


@pytest.fixture
async def with_image(edit, tmp_path):
    path = tmp_path / "green.png"
    await _image(path, "lime")
    ingested = await ingest_files([path])
    edit.project.assets.append(ingested.assets[0])
    edit.save(edit.project)
    return edit, ingested.assets[0]


async def test_images_import_as_still_assets(tmp_path):
    for name in ("card.png", "photo.jpg"):
        await _image(tmp_path / name, "orange")
    result = await ingest_files([tmp_path / "card.png", tmp_path / "photo.jpg"])
    assert not result.failures
    for asset in result.assets:
        assert asset.probe.still and asset.probe.duration_us == 0
        assert asset.probe.video is not None and asset.probe.video.width == 320
        assert asset.probe.audio_streams == []
    assert {".png", ".jpg", ".jpeg", ".webp", ".tiff"} <= MEDIA_EXTENSIONS


def _still(asset_id: str, start: int, length: int, **extra) -> EditorClip:
    return EditorClip(
        id="still",
        kind="video",
        asset_id=asset_id,
        name="Green",
        start=start,
        source_in=0,
        source_out=length,
        transform=Transform(width=160, height=90),
        **{"still_frame": 0, **extra},
    )


def test_still_clips_have_no_source_limit_and_must_be_still(with_image):
    bundle, image = with_image
    red = bundle.project.assets[0]
    long_still = EditorDocument(clips=[_still(image.id, 0, 10_000)])
    validate_assets(long_still, bundle.project)
    moving = EditorDocument(
        clips=[_still(image.id, 0, 50).model_copy(update={"still_frame": None})]
    )
    with pytest.raises(ValueError, match="still image"):
        validate_assets(moving, bundle.project)
    # A freeze frame of a video holds a frame that must exist.
    beyond = EditorDocument(clips=[_still(red.id, 0, 50, still_frame=999)])
    with pytest.raises(ValueError, match="beyond its source"):
        validate_assets(beyond, bundle.project)
    with pytest.raises(ValueError, match="normal speed"):
        _still(image.id, 0, 50, speed=2)
    with pytest.raises(ValueError, match="Only video clips"):
        EditorClip(
            id="a", kind="audio", asset_id=red.id, name="a", start=0, source_in=0,
            source_out=5, still_frame=0,
        )  # fmt: skip


async def test_still_image_renders_for_its_length_and_dissolves_with_full_handles(
    with_image, tmp_path
):
    bundle, image = with_image
    red = bundle.project.assets[0]
    doc = EditorDocument(
        clips=[
            EditorClip(
                id="red",
                kind="video",
                asset_id=red.id,
                name="Red",
                start=0,
                source_in=10,
                source_out=35,
                transform=Transform(width=160, height=90),
            ),
            # Longer than any source: a still has no source limit.
            _still(image.id, 25, 100),
        ],
        transitions=[
            EditorTransition(id="t", left_id="red", right_id="still", duration=10),
        ],
    )
    project, _ = SetEditor(document=doc).apply(bundle.project)
    bundle.save(project)
    output = await render_project(bundle.project, bundle, hw="cpu", normalize=False)
    probe = await ffmpeg.probe(output.path)
    assert probe.video.nb_frames == 125
    middle = (await pixels(output.path, 25, tmp_path)).reshape(-1, 3).mean(axis=0)
    late = (await pixels(output.path, 120, tmp_path)).reshape(-1, 3).mean(axis=0)
    # The dissolve uses the still's head handle: red and green mix at the cut.
    assert 60 < middle[0] < 200 and 60 < middle[1] < 220
    assert late[1] > 200 and late[0] < 60 and late[2] < 60


async def test_freeze_frame_renders_the_held_source_frame(edit, tmp_path):
    exe = locate_binaries().ffmpeg
    ramp = tmp_path / "ramp.mp4"
    # Brightness rises with the frame number: frame n has a grey level of about 4 n.
    await asyncio.to_thread(
        subprocess.run,
        [str(exe), "-v", "error", "-y", "-f", "lavfi", "-i", "color=black:s=160x90:r=25:d=2"]
        + ["-vf", "geq=lum='4*N':cb=128:cr=128", "-c:v", "libx264", "-qp", "0"]
        + ["-pix_fmt", "yuv420p", str(ramp)],
        check=True,
        capture_output=True,
        creationflags=NO_WINDOW,
    )
    asset = (await ingest_files([ramp])).assets[0]
    edit.project.assets.append(asset)
    doc = EditorDocument(clips=[_still(asset.id, 0, 30, still_frame=40)])
    project, _ = SetEditor(document=doc).apply(edit.project)
    edit.save(project)
    output = await render_project(edit.project, edit, hw="cpu", normalize=False)
    first = (await pixels(output.path, 0, tmp_path)).mean()
    last = (await pixels(output.path, 29, tmp_path)).mean()
    assert abs(first - 160) < 12 and abs(last - first) < 3


def test_camtasia_exports_images_as_imfile(with_image):
    bundle, image = with_image
    doc = EditorDocument(clips=[_still(image.id, 0, 75)])
    project, _ = SetEditor(document=doc).apply(bundle.project)
    data = json.loads(export_camtasia(project).text)
    media = data["timeline"]["sceneTrack"]["scenes"][0]["csml"]["tracks"][0]["medias"][0]
    assert media["_type"] == "IMFile"
    assert media["mediaStart"] == 0 and media["mediaDuration"] == 1
    assert media["duration"] == 75 * 705_600_000 // 25
    entry = next(e for e in data["sourceBin"] if e["id"] == media["src"])
    assert entry["sourceTracks"] == [
        {
            "range": [0, 1],
            "trackRect": [0, 0, 320, 180],
            "bitDepth": 24,
            "numChannels": 0,
            "integratedLUFS": 100.0,
            "peakLevel": -1.0,
            "metaData": "green.png;",
            "type": 1,
            "editRate": 10_000_000,
            "sampleRate": 0,
        }
    ]


def test_every_export_format_accepts_still_clips(with_image, tmp_path):
    import opentimelineio as otio

    from videoflow.exporters.service import FORMATS, export_project

    bundle, image = with_image
    red = bundle.project.assets[0]
    doc = EditorDocument(
        clips=[
            EditorClip(
                id="red", kind="video", asset_id=red.id, name="Red", start=0,
                source_in=0, source_out=25, transform=Transform(width=160, height=90),
            ),
            _still(image.id, 25, 75),
        ]
    )  # fmt: skip
    project, _ = SetEditor(document=doc).apply(bundle.project)
    paths = export_project(project, tmp_path / "out", sorted(FORMATS), transcripts={})
    assert paths
    timeline = otio.adapters.read_from_file(str(tmp_path / "out" / "edit.otio"))
    clip = next(c for c in timeline.find_clips() if c.name == "green.png")
    assert clip.media_reference.available_range is None
    assert clip.source_range.duration.value == 75
    assert clip.metadata["videoflow"]["stillFrame"] == 0


def test_freeze_frames_export_as_freeze_effects(edit, tmp_path):
    import opentimelineio as otio

    from videoflow.exporters.service import export_project

    red = edit.project.assets[0]
    doc = EditorDocument(
        clips=[
            EditorClip(
                id="red", kind="video", asset_id=red.id, name="Red", start=0,
                source_in=0, source_out=25, transform=Transform(width=160, height=90),
            ),
            _still(red.id, 25, 50, still_frame=24).model_copy(update={"id": "freeze"}),
        ]
    )  # fmt: skip
    project, _ = SetEditor(document=doc).apply(edit.project)
    export_project(project, tmp_path / "out", ["otio", "edl", "camtasia"])
    timeline = otio.adapters.read_from_file(str(tmp_path / "out" / "edit.otio"))
    freeze = [c for c in timeline.find_clips() if c.effects][0]
    assert isinstance(freeze.effects[0], otio.schema.FreezeFrame)
    assert freeze.source_range.start_time.value == 24
    edl = (tmp_path / "out" / "edit.edl").read_text()
    assert "000.0" in edl and edl.count("M2") == 1
    tscproj = json.loads((tmp_path / "out" / "edit.tscproj").read_text())
    medias = tscproj["timeline"]["sceneTrack"]["scenes"][0]["csml"]["tracks"][0]["medias"]
    held = next(m for m in medias if m["_type"] == "IMFile")
    assert held["mediaStart"] == 24 * 705_600_000 // 25 and held["mediaDuration"] == 1


def test_freeze_frame_edl_reads_back_as_a_freeze(edit, tmp_path):
    import opentimelineio as otio

    from videoflow.exporters.service import export_project

    red = edit.project.assets[0]
    doc = EditorDocument(
        clips=[
            EditorClip(
                id="red", kind="video", asset_id=red.id, name="Red", start=0,
                source_in=0, source_out=25, transform=Transform(width=160, height=90),
            ),
            _still(red.id, 25, 50, still_frame=24).model_copy(update={"id": "freeze"}),
        ]
    )  # fmt: skip
    project, _ = SetEditor(document=doc).apply(edit.project)
    export_project(project, tmp_path / "out", ["edl"])
    text = (tmp_path / "out" / "edit.edl").read_text()
    timeline = otio.adapters.read_from_string(text, "cmx_3600", rate=25)
    clips = list(timeline.find_clips())
    assert [c.duration().value for c in clips] == [25, 50]
    assert any(isinstance(e, otio.schema.FreezeFrame) for e in clips[1].effects)
