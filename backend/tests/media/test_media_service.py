from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from tests.media.conftest import run_ffprobe
from videoflow.core import ids
from videoflow.media import ffmpeg
from videoflow.media.caps import get_caps, locate_binaries
from videoflow.media.hashing import FULL_HASH_LIMIT, cache_key, content_hash_sync
from videoflow.media.ingest import ingest_files, ingest_folder, prepare_asset, scan_media
from videoflow.media.peaks import SAMPLE_RATE, compute_peaks, read_peaks
from videoflow.media.proxy import build_proxy, proxy_fps, proxy_size
from videoflow.media.thumbs import build_thumbs, thumb_count
from videoflow.project.store import Bundle


def _keyframe_times(path: Path) -> list[float]:
    out = run_ffprobe(
        "-select_streams", "v:0", "-show_entries", "packet=pts_time,flags", "-of", "csv=p=0",
        str(path),
    )  # fmt: skip
    return [float(line.split(",")[0]) for line in out.splitlines() if "K" in line.split(",")[1]]


def _frame_times(path: Path) -> list[float]:
    out = run_ffprobe(
        "-select_streams", "v:0", "-show_entries", "frame=pts_time", "-of", "csv=p=0", str(path)
    )  # fmt: skip
    return sorted(float(x.rstrip(",")) for x in out.split())


# ------------------------------------------------------------------ hashing


def test_hash_stable_and_content_sensitive(tmp_path: Path) -> None:
    a, b, c = (tmp_path / n for n in "abc")
    a.write_bytes(b"hello" * 1000)
    b.write_bytes(b"hello" * 1000)
    c.write_bytes(b"hellp" * 1000)
    assert content_hash_sync(a) == content_hash_sync(b) != content_hash_sync(c)
    assert len(content_hash_sync(a)) == 40
    assert cache_key("ab" * 20, "x", 1) != cache_key("ab" * 20, "x", 2)


def test_hash_large_file_is_sampled(tmp_path: Path) -> None:
    f = tmp_path / "big.bin"
    with f.open("wb") as fh:
        fh.truncate(FULL_HASH_LIMIT + 5_000_000)
    h1 = content_hash_sync(f)
    with f.open("r+b") as fh:  # change the last bytes: sampled chunk includes the tail
        fh.seek(-10, 2)
        fh.write(b"x" * 10)
    assert content_hash_sync(f) != h1


# ------------------------------------------------------------------ ingest


async def test_ingest_folder_assets_and_duplicates(samples_dir: Path, tmp_path: Path) -> None:
    work = tmp_path / "rushes"
    work.mkdir()
    for n in ("clip_vfr.mp4", "clip_hlg.mp4", "clip_vertical_1080x1920_24_noaudio.mp4"):
        shutil.copy(samples_dir / n, work / n)
    shutil.copy(samples_dir / "clip_vfr.mp4", work / "copy_of_vfr.mp4")
    (work / "notes.txt").write_text("x")
    (work / "broken.mp4").write_bytes(b"not a video")

    res = await ingest_folder(work, base_dir=tmp_path)
    names = {Path(a.path).name: a for a in res.assets}
    assert set(names) == {"clip_vfr.mp4", "clip_hlg.mp4", "clip_vertical_1080x1920_24_noaudio.mp4"}
    assert [Path(d.path).name for d in res.duplicates] == ["copy_of_vfr.mp4"]
    assert [Path(f.path).name for f in res.failures] == ["broken.mp4"]
    assert all(ids.is_id(a.id, ids.ASSET) for a in res.assets)
    assert names["clip_vfr.mp4"].rel_path == "rushes/clip_vfr.mp4"
    assert names["clip_vfr.mp4"].probe.video is not None
    assert names["clip_vfr.mp4"].probe.video.vfr is True
    assert names["clip_hlg.mp4"].probe.video.hdr == "hlg"  # type: ignore[union-attr]
    vert = names["clip_vertical_1080x1920_24_noaudio.mp4"].probe
    assert not vert.has_audio and vert.duration_us > 0

    # a second ingest against the known assets skips everything
    again = await ingest_files(scan_media(work), known=res.assets)
    assert not again.assets
    assert {Path(d.path).name for d in again.duplicates} == {
        "clip_vfr.mp4", "clip_hlg.mp4", "clip_vertical_1080x1920_24_noaudio.mp4",
        "copy_of_vfr.mp4",
    }  # fmt: skip
    assert all(d.of_asset_id for d in again.duplicates if d.path.name != "copy_of_vfr.mp4")


# ------------------------------------------------------------------ proxy


def test_proxy_size_and_fps() -> None:
    assert proxy_size(1920, 1080) == (960, 540)
    assert proxy_size(1080, 1920) == (540, 960)
    assert proxy_size(640, 360) == (640, 360)  # never upscaled
    assert proxy_size(3840, 2160, 720) == (1280, 720)


@pytest.fixture(scope="module")
def proxies(samples_dir: Path, tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("proxies")


async def test_proxy_cfr_540_keyframes(samples_dir: Path, proxies: Path) -> None:
    src = samples_dir / "cam_a_720p25_stereo.mp4"
    h = content_hash_sync(src)
    r = await build_proxy(src, proxies, h, hw="cpu")
    assert r is not None and not r.cached and r.encoder == "libx264"
    pr = await ffmpeg.probe(r.path)
    v = pr.video
    assert v is not None
    assert (v.width, v.height) == (960, 540) and v.codec == "h264"
    assert v.pix_fmt == "yuv420p" and not v.is_vfr and v.fps == 25
    assert pr.audio and pr.audio[0].channels == 2 and pr.audio[0].sample_rate == 48000
    keys = _keyframe_times(r.path)
    gaps = np.diff(keys)
    assert keys[0] == 0 and len(keys) >= 7
    assert np.all(gaps > 0.9) and np.all(gaps < 1.1)
    assert r.time_aligned
    again = await build_proxy(src, proxies, h, hw="cpu")
    assert again is not None and again.cached and again.path == r.path


async def test_proxy_vfr_becomes_cfr(samples_dir: Path, proxies: Path) -> None:
    src = samples_dir / "clip_vfr.mp4"
    r = await build_proxy(src, proxies, content_hash_sync(src), hw="cpu")
    assert r is not None
    v = (await ffmpeg.probe(r.path)).video
    assert v is not None and not v.is_vfr and v.fps == 30
    steps = np.diff(_frame_times(r.path))
    assert np.allclose(steps, 1 / 30, atol=1e-3)
    assert r.time_aligned


async def test_proxy_hlg_tone_mapped_to_bt709(samples_dir: Path, proxies: Path) -> None:
    caps = get_caps()
    if not (caps.has_filter("zscale") and caps.has_filter("tonemap")):
        pytest.skip("zscale/tonemap not available")
    src = samples_dir / "clip_hlg.mp4"
    r = await build_proxy(src, proxies, content_hash_sync(src), hw="cpu")
    assert r is not None and r.tone_mapped
    v = (await ffmpeg.probe(r.path)).video
    assert v is not None
    assert (v.color_transfer, v.color_primaries, v.color_space) == ("bt709",) * 3
    assert v.pix_fmt == "yuv420p" and not v.is_hdr and v.bit_depth in (None, 8)


async def test_proxy_bakes_rotation(rotated_clip: Path, proxies: Path) -> None:
    src_probe = await ffmpeg.probe(rotated_clip)
    assert src_probe.video is not None and src_probe.video.rotation in (90, 270)
    r = await build_proxy(rotated_clip, proxies, content_hash_sync(rotated_clip), hw="cpu")
    assert r is not None
    v = (await ffmpeg.probe(r.path)).video
    assert v is not None and v.rotation == 0
    assert v.height > v.width and (v.width, v.height) == (r.width, r.height)  # portrait baked


async def test_proxy_video_less_is_none(samples_dir: Path, proxies: Path) -> None:
    wav = proxies / "a.wav"
    subprocess.run(  # noqa: ASYNC221
        [str(locate_binaries().ffmpeg), "-v", "error", "-y", "-f", "lavfi", "-i",
         "sine=d=0.5", str(wav)],
        check=True,
    )  # fmt: skip
    assert await build_proxy(wav, proxies, content_hash_sync(wav), hw="cpu") is None


def test_proxy_fps_rules() -> None:
    from fractions import Fraction

    class V:  # minimal stand-in for VideoStreamInfo
        def __init__(self, fps: Fraction, r: Fraction, vfr: bool) -> None:
            self.fps, self.r_fps, self.is_vfr = fps, r, vfr

    assert proxy_fps(V(Fraction(30000, 1001), Fraction(30000, 1001), False)) == Fraction(  # type: ignore[arg-type]
        30000, 1001
    )
    assert proxy_fps(V(Fraction(215, 10), Fraction(30), True)) == 30  # type: ignore[arg-type]
    assert proxy_fps(V(Fraction(120), Fraction(120), False)) == 60  # type: ignore[arg-type]


# ------------------------------------------------------------------ thumbs


async def test_thumbs_one_per_two_seconds_with_index(samples_dir: Path, tmp_path: Path) -> None:
    src = samples_dir / "cam_a_720p25_stereo.mp4"
    pr = await ffmpeg.probe(src)
    assert pr.video is not None and pr.duration_us is not None
    kw: dict[str, Any] = {"display_size": pr.video.display_size, "duration_us": pr.duration_us}
    r = await build_thumbs(src, tmp_path, "ab" * 20, **kw)
    idx = json.loads(r.index_path.read_text())
    assert idx["intervalUs"] == 2_000_000 and idx["thumbWidth"] == 160
    assert idx["count"] == thumb_count(pr.duration_us) == 4
    assert idx["thumbHeight"] == 90
    sheet = r.directory / idx["sheets"][0]
    assert sheet.is_file()
    sp = await ffmpeg.probe(sheet)
    assert sp.video is not None
    assert (sp.video.width, sp.video.height) == (160 * idx["cols"], 90 * idx["rows"])
    assert (await build_thumbs(src, tmp_path, "ab" * 20, **kw)).cached


# ------------------------------------------------------------------ peaks


async def test_peaks_match_rms_reference(samples_dir: Path, tmp_path: Path) -> None:
    src = samples_dir / "retake_en.mp4"
    out = tmp_path / "p.bin"
    r = await compute_peaks(src, out)
    assert not r.cached and r.peaks_per_second == 100
    pcm = subprocess.run(  # noqa: ASYNC221
        [str(locate_binaries().ffmpeg), "-v", "error", "-i", str(src), "-map", "0:a:0", "-ac", "1",
         "-ar", str(SAMPLE_RATE), "-f", "f32le", "-"],
        capture_output=True, check=True,
    ).stdout  # fmt: skip
    x = np.frombuffer(pcm, "<f4")
    bucket = SAMPLE_RATE // 100
    n = len(x) // bucket
    ref = np.sqrt((x[: n * bucket].reshape(n, bucket) ** 2).mean(axis=1))
    p = read_peaks(out)
    assert p.count == -(-len(x) // bucket) == r.count
    full_scale = 1.0
    assert np.max(np.abs(p.rms[:n] - ref)) <= 0.01 * full_scale
    assert abs(float(np.sqrt((p.rms[:n] ** 2).mean())) - float(np.sqrt((ref**2).mean()))) <= (
        0.01 * float(np.sqrt((ref**2).mean()))
    )
    ref_max = x[: n * bucket].reshape(n, bucket).max(axis=1)
    assert np.max(np.abs(p.max[:n] - ref_max)) <= 1e-3
    assert float(p.max.max()) > 0.05  # speech present
    assert (await compute_peaks(src, out)).cached


async def test_peaks_cancel(samples_dir: Path, tmp_path: Path) -> None:
    import asyncio

    from videoflow.media.errors import MediaCancelled

    ev = asyncio.Event()
    ev.set()
    with pytest.raises(MediaCancelled):
        await compute_peaks(samples_dir / "retake_en.mp4", tmp_path / "c.bin", cancel=ev)
    assert not (tmp_path / "c.bin").exists()


# ------------------------------------------------------------------ prepare_asset


async def test_prepare_asset_and_second_run_cached(
    samples_dir: Path, samples_manifest: dict[str, Any], tmp_path: Path
) -> None:
    bundle = Bundle(tmp_path / "p.videoflow")
    for d in bundle.directories():
        d.mkdir(parents=True, exist_ok=True)
    res = await ingest_files([samples_dir / "clip_480p2997_mono.mp4"])
    asset = res.assets[0]
    first = await prepare_asset(bundle, asset, hw="cpu")
    assert first.proxy and first.thumbs and first.peaks and not first.fully_cached
    assert first.proxy.path.is_file() and first.peaks.path.is_file()
    second = await prepare_asset(bundle, asset, hw="cpu")
    assert second.fully_cached
    assert second.proxy and second.proxy.path == first.proxy.path


async def test_proxy_auto_hw_falls_back_to_software(samples_dir: Path, proxies: Path) -> None:
    src = samples_dir / "broll_a1.mp4"
    r = await build_proxy(src, proxies, content_hash_sync(src), hw="auto")
    assert r is not None and r.path.is_file()
    assert (await ffmpeg.probe(r.path)).video is not None
