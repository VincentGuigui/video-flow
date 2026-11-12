"""Preview media in two stages: quick stills and sound, then the WebM in the background
(docs/features/import-analysis/importing.md#preview-media)."""

import asyncio
import hashlib
import subprocess
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from videoflow.api.app import create_app
from videoflow.editor import previews as module
from videoflow.editor.previews import Previews, plays_as_is
from videoflow.media import ffmpeg
from videoflow.media.caps import NO_WINDOW, locate_binaries
from videoflow.media.ingest import ingest_files
from videoflow.project.library import ProjectLibrary
from videoflow.project.models import new_project
from videoflow.project.store import Bundle


def _make(path: Path, *args: str) -> Path:
    subprocess.run(
        [str(locate_binaries().ffmpeg), "-v", "error", "-y", *args, str(path)],
        check=True,
        capture_output=True,
        creationflags=NO_WINDOW,
    )
    return path


@pytest.fixture
def clip(tmp_path) -> Path:
    """5 s, 25 fps, a keyframe every second, with sound."""
    (tmp_path / "media").mkdir()
    return _make(
        tmp_path / "media" / "take.mp4",
        "-f", "lavfi", "-i", "testsrc2=s=640x360:r=25:d=5",
        "-f", "lavfi", "-i", "sine=f=440:d=5",
        "-c:v", "libx264", "-g", "25", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest",
    )  # fmt: skip


async def _bundle(tmp_path: Path, *sources: Path) -> Bundle:
    bundle = Bundle.create(tmp_path / "edit.video-flow", new_project("Previews"))
    bundle.project.assets = (await ingest_files(list(sources))).assets
    bundle.save(bundle.project)
    return bundle


async def test_quick_pass_gives_a_still_per_second_and_the_sound(tmp_path, clip):
    bundle = await _bundle(tmp_path, clip)
    asset = bundle.project.assets[0]
    previews = Previews(bundle)
    assert previews.status(asset).state == "pending"
    steps: list[float] = []
    await previews.quick(asset, clip, steps.append)
    status = previews.status(asset)
    assert status.state == "stills" and status.audio and not status.video
    assert 4 <= status.stills <= 5
    # A time past the end gives the last still; a negative one the first.
    assert previews.still_path(asset, 99) == previews.still_path(asset, status.stills - 1)
    assert previews.still_path(asset, -3) == previews.still_path(asset, 0)
    audio = await ffmpeg.probe(previews.audio_path(asset))
    assert audio.audio and audio.audio[0].codec == "opus" and audio.video is None


async def test_background_video_replaces_the_quick_pass(tmp_path, clip):
    bundle = await _bundle(tmp_path, clip)
    asset = bundle.project.assets[0]
    previews = Previews(bundle)
    previews.enqueue([asset.id])
    for _ in range(600):
        if previews.status(asset).state == "ready":
            break
        await asyncio.sleep(0.05)
    status = previews.status(asset)
    assert status.state == "ready" and status.video and status.stills == 0 and not status.audio
    assert not previews.folder(asset).exists()
    video = await ffmpeg.probe(previews.video_path(asset))
    assert video.video.codec == "vp9" and video.video.height == 360
    assert video.audio[0].codec == "opus"
    await previews.close()


async def test_queue_order_and_priority(tmp_path, clip, monkeypatch):
    other = _make(
        clip.parent / "other.mp4",
        "-f", "lavfi", "-i", "color=red:s=320x240:r=25:d=2", "-c:v", "libx264",
    )  # fmt: skip
    bundle = await _bundle(tmp_path, clip, other)
    first, second = bundle.project.assets
    previews = Previews(bundle)
    started = asyncio.Event()
    release = asyncio.Event()

    async def slow(asset):
        started.set()
        await release.wait()

    monkeypatch.setattr(previews, "_prepare", slow)
    previews.enqueue([first.id, second.id])
    await started.wait()
    assert previews.current == first.id and previews.queue == [second.id]
    previews.enqueue([second.id])  # already queued: unchanged
    previews.enqueue([first.id], first=True)  # being made: unchanged
    assert previews.queue == [second.id]
    release.set()
    await previews.close()


async def test_earlier_webm_previews_are_reused(tmp_path, clip):
    bundle = await _bundle(tmp_path, clip)
    asset = bundle.project.assets[0]
    legacy = hashlib.sha256((asset.content_hash + ":webm-v1").encode()).hexdigest()[:24]
    bundle.proxies_dir.mkdir(parents=True, exist_ok=True)
    (bundle.proxies_dir / f"{legacy}.webm").write_bytes(b"webm")
    previews = Previews(bundle)
    assert previews.status(asset).state == "ready"
    previews.enqueue([asset.id])
    assert previews.queue == [] and previews.task is None


async def test_playable_audio_and_images_need_no_preview(tmp_path):
    wav = _make(tmp_path / "voice.wav", "-f", "lavfi", "-i", "sine=f=300:d=1")
    m4a = _make(tmp_path / "voice.m4a", "-f", "lavfi", "-i", "sine=f=300:d=1", "-c:a", "aac")
    png = _make(tmp_path / "card.png", "-f", "lavfi", "-i", "color=blue:s=64x64", "-frames:v", "1")
    assets = (await ingest_files([wav, m4a, png])).assets
    by_name = {Path(a.path).name: a for a in assets}
    assert plays_as_is(by_name["voice.wav"]) and plays_as_is(by_name["card.png"])
    assert not plays_as_is(by_name["voice.m4a"])  # AAC: Qt WebEngine cannot play it


def _client(tmp_path, bundle):
    app = create_app(
        bundle,
        token="t",
        desktop_secret="s",
        media_roots=[tmp_path],
        library=ProjectLibrary(tmp_path / "recent.json"),
    )
    client = TestClient(app, base_url="http://127.0.0.1:8765")
    return app, client


def _wait(client, asset_id, states):
    for _ in range(600):
        state = client.get("/api/previews").json()[asset_id]
        if state["state"] in states:
            return state
        time.sleep(0.05)
    raise AssertionError(f"preview stayed {state}")


def test_api_serves_stills_and_sound_while_the_video_is_made(tmp_path, clip, monkeypatch):
    bundle = asyncio.run(_bundle(tmp_path, clip))
    asset = bundle.project.assets[0]

    async def never(self, asset, source):  # the background video never finishes here
        await asyncio.Event().wait()

    monkeypatch.setattr(module.Previews, "_encode", never)
    _, client = _client(tmp_path, bundle)
    with client:
        client.get("/?token=t", follow_redirects=False)
        state = _wait(client, asset.id, ("stills",))  # queued at start, quick pass done
        assert state["stills"] >= 4 and state["audio"] and not state["video"]
        assert client.get(f"/api/media/{asset.id}").status_code == 200  # the sound for now
        still = client.get(f"/api/previews/{asset.id}/still/2")
        assert still.status_code == 200 and still.content[:2] == b"\xff\xd8"
        audio = client.get(f"/api/previews/{asset.id}/audio", headers={"Range": "bytes=0-3"})
        assert audio.status_code == 206 and audio.content == b"\x1aE\xdf\xa3"
        assert client.get(f"/api/thumbnail/{asset.id}").status_code == 200


def test_api_serves_the_video_once_ready(tmp_path, clip):
    bundle = asyncio.run(_bundle(tmp_path, clip))
    asset = bundle.project.assets[0]
    _, client = _client(tmp_path, bundle)
    with client:
        client.get("/?token=t", follow_redirects=False)
        _wait(client, asset.id, ("ready",))
        media = client.get(f"/api/media/{asset.id}", headers={"Range": "bytes=0-3"})
        assert media.status_code == 206 and media.content == b"\x1aE\xdf\xa3"  # WebM
        assert client.get(f"/api/previews/{asset.id}/still/0").status_code == 404
