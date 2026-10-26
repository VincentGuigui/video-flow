import asyncio
import json
import subprocess
from pathlib import Path

import numpy as np
import pytest

from videoflow.core.time import Rational
from videoflow.editor.models import EditorClip, EditorDocument, Transform
from videoflow.media import ffmpeg
from videoflow.media.caps import NO_WINDOW, locate_binaries
from videoflow.media.ingest import ingest_files
from videoflow.project.commands import SetEditor
from videoflow.project.models import ProjectSettings, new_project
from videoflow.project.store import Bundle
from videoflow.render.graph import compile_graph
from videoflow.render.loudness import measurement
from videoflow.render.runner import render_project


@pytest.fixture
async def edit(tmp_path):
    exe = locate_binaries().ffmpeg
    sources = []
    for name, color, audio in (("red", "red", True), ("blue", "blue", False)):
        path = tmp_path / f"{name}.mp4"
        args = [
            str(exe),
            "-v",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"color={color}:s=160x90:r=25:d=3",
        ]
        if audio:
            args += ["-f", "lavfi", "-i", "sine=frequency=600:sample_rate=48000:duration=3"]
        args += ["-c:v", "libx264", "-threads", "1", "-pix_fmt", "yuv420p"]
        if audio:
            args += ["-c:a", "aac"]
        await asyncio.to_thread(
            subprocess.run,
            [*args, str(path)],
            check=True,
            capture_output=True,
            creationflags=NO_WINDOW,
        )
        sources.append(path)
    ingested = await ingest_files(sources)
    project = new_project("Render test")
    project.settings = ProjectSettings(width=160, height=90, frame_rate=Rational.of(25))
    project.assets = ingested.assets
    red, blue = (a.id for a in project.assets)
    doc = EditorDocument(
        clips=[
            EditorClip(
                id="base",
                kind="video",
                asset_id=red,
                name="Red",
                start=0,
                source_in=10,
                source_out=60,
                link_id="pair",
                transform=Transform(width=160, height=90),
            ),
            EditorClip(
                id="audio",
                kind="audio",
                asset_id=red,
                name="Audio",
                start=0,
                source_in=10,
                source_out=60,
                link_id="pair",
                gain_db=-6,
            ),
            EditorClip(
                id="blue",
                kind="video",
                asset_id=blue,
                name="Blue",
                start=10,
                source_in=0,
                source_out=20,
                layer=2,
                transform=Transform(x=40, width=80, height=90, crop_left=0.5),
            ),
            EditorClip(
                id="disabled",
                kind="video",
                asset_id=blue,
                name="Disabled",
                start=0,
                source_in=0,
                source_out=50,
                layer=3,
                enabled=False,
            ),
            EditorClip(id="gap", kind="gap", name="Empty", start=50, source_in=0, source_out=25),
        ]
    )
    project, _ = SetEditor(document=doc).apply(project)
    return Bundle.create(tmp_path / "test.videoflow", project)


async def pixels(path, frame, folder, rate=25):
    target = folder / f"frame-{frame}.rgb"
    result = await ffmpeg.run(
        [
            "-y",
            "-i",
            str(path),
            "-vf",
            f"select=eq(n\\,{frame})",
            "-frames:v",
            "1",
            "-pix_fmt",
            "rgb24",
            "-f",
            "rawvideo",
            str(target),
        ]
    )
    assert result.ok, result.stderr_tail
    return np.frombuffer(target.read_bytes(), dtype=np.uint8).reshape(90, 160, 3)


@pytest.mark.parametrize("mode, expected", [("color", 1), ("blur", 2), ("transparent", 0)])
async def test_clip_background_color_blur_and_transparent_layers(edit, tmp_path, mode, expected):
    from videoflow.editor.models import Background
    from videoflow.editor.resolve import editable_document

    document = editable_document(edit.project)
    overlay = next(c for c in document.clips if c.id == "blue")
    overlay.background = Background(mode=mode, color="#00ff00")
    project, _ = SetEditor(document=document).apply(edit.project)
    output = await render_project(project, edit, hw="cpu", normalize=False)
    frame = await pixels(output.path, 10, tmp_path)
    # Outside the foreground crop: backdrop color/blur or the red lower layer.
    pixel = frame[45, 10]
    assert pixel[expected] > 180, pixel
    assert frame[45, 90, 2] > 180  # foreground remains blue
    previous = await pixels(output.path, 9, tmp_path)
    assert previous[45, 10, 0] > 180  # background obeys the clip's time range


async def test_render_originals_layer_crop_gap_and_exact_frames(edit, tmp_path):
    before = edit.project.dump()
    output = await render_project(edit.project, edit, hw="cpu", normalize=False)
    probe = await ffmpeg.probe(output.path)
    assert probe.video.nb_frames == 75
    assert probe.video.fps == 25
    assert abs(probe.audio[0].duration_us - 3_000_000) <= 40_000
    for frame in (9, 10, 29, 30, 50, 74):
        picture = await pixels(output.path, frame, tmp_path)
        center = picture[45, 100].astype(int)
        edge = picture[45, 10].astype(int)
        if frame in (10, 29):
            assert center[2] > 200 and center[0] < 40, (frame, center)
        elif frame < 50:
            assert center[0] > 200 and center[2] < 40, (frame, center)
        else:
            assert max(center) < 12 and max(edge) < 12
        if frame < 50:
            assert edge[0] > 200 and edge[2] < 40
    assert edit.project.dump() == before
    log = json.loads(output.report.read_bytes())
    assert log["actualFrames"] == 75 and log["state"] == "done"
    assert not list(edit.renders_dir.glob("*.part.mp4"))


async def test_audio_only_and_silent_normalization(edit):
    project = edit.project.model_copy(deep=True)
    raw = project.model_extra["editor"]
    raw["clips"] = [c for c in raw["clips"] if c["kind"] == "audio"]
    raw["clips"][0]["linkId"] = None
    raw["clips"][0]["gainDb"] = -6
    result = await render_project(project, edit, hw="cpu", normalize=True)
    assert result.path.is_file()
    report = json.loads(result.report.read_bytes())
    assert report["loudness"] is not None
    assert report["actualFrames"] == 50


async def test_ntsc_quantization(edit):
    project = edit.project.model_copy(deep=True)
    project.settings.frame_rate = Rational.of(30000, 1001)
    output = await render_project(project, edit, hw="cpu", normalize=False)
    probe = await ffmpeg.probe(output.path)
    assert probe.video.nb_frames == 75
    assert probe.video.fps == Rational.of(30000, 1001).fraction
    assert abs(probe.audio[0].duration_us - 2_502_500) <= 34_367


async def test_cancel_removes_partial_and_keeps_previous_renders(edit, monkeypatch):
    started = asyncio.Event()

    async def slow(*args, **kwargs):
        started.set()
        await asyncio.sleep(60)

    monkeypatch.setattr("videoflow.render.runner.ffmpeg.run", slow)
    old = edit.renders_dir / "previous.mp4"
    old.write_bytes(b"keep")
    task = asyncio.create_task(render_project(edit.project, edit, hw="cpu", normalize=False))
    await asyncio.wait_for(started.wait(), 5)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert old.read_bytes() == b"keep"
    assert list(edit.renders_dir.glob("render-*.mp4")) == []
    logs = list(edit.renders_dir.glob("*.log.json"))
    assert json.loads(logs[0].read_bytes())["state"] == "cancelled"


async def test_offline_source_fails_before_output_and_draft_dimensions(edit):
    graph = compile_graph(edit.project, "draft")
    assert (graph.width, graph.height) == (160, 90)
    await asyncio.to_thread(Path(edit.project.assets[0].path).unlink)
    with pytest.raises(FileNotFoundError, match="offline"):
        await render_project(edit.project, edit, hw="cpu")
    assert list(edit.renders_dir.iterdir()) == []


def test_digital_silence_skips_invalid_loudnorm_filter():
    assert measurement('{"input_i":"-inf", "input_tp":"-inf"}') is None
    with pytest.raises(ValueError, match="measurements"):
        measurement("no JSON")

