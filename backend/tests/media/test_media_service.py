from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest

from tests.media.conftest import run_ffprobe
from videoflow.core import ids
from videoflow.media import ffmpeg
from videoflow.media.caps import get_caps, locate_binaries
from videoflow.media.hashing import FULL_HASH_LIMIT, cache_key, content_hash_sync
from videoflow.media.ingest import ingest_files, ingest_folder, scan_media
from videoflow.media.peaks import SAMPLE_RATE, compute_peaks, read_peaks
from videoflow.media.proxy import proxy_fps, proxy_size


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


async def _preview(src: Path, tmp_path: Path) -> Path:
    """The background preview video of `src` (docs/features/import-analysis/importing.md)."""
    from videoflow.editor.previews import Previews
    from videoflow.project.models import new_project
    from videoflow.project.store import Bundle

    bundle = Bundle.create(tmp_path / f"{src.stem}.video-flow", new_project("Preview"))
    bundle.project.assets = (await ingest_files([src])).assets
    asset = bundle.project.assets[0]
    previews = Previews(bundle)
    await previews._encode(asset, src)
    path = previews.video_path(asset)
    assert path is not None
    return path


async def test_preview_cfr_540_keyframes(samples_dir: Path, tmp_path: Path) -> None:
    src = samples_dir / "cam_a_720p25_stereo.mp4"
    path = await _preview(src, tmp_path)
    pr = await ffmpeg.probe(path)
    v = pr.video
    assert v is not None
    assert (v.width, v.height) == (960, 540) and v.codec == "vp9"
    assert v.pix_fmt == "yuv420p" and v.fps == 25
    assert pr.audio and pr.audio[0].channels == 2 and pr.audio[0].sample_rate == 48000
    keys = _keyframe_times(path)
    gaps = np.diff(keys)
    assert keys[0] == 0 and len(keys) >= 7
    assert np.all(gaps > 0.9) and np.all(gaps < 1.1)
    source = await ffmpeg.probe(src)
    assert pr.duration_us and source.duration_us
    assert abs(pr.duration_us - source.duration_us) <= 100_000  # preview time = source time


async def test_preview_vfr_becomes_cfr(samples_dir: Path, tmp_path: Path) -> None:
    path = await _preview(samples_dir / "clip_vfr.mp4", tmp_path)
    v = (await ffmpeg.probe(path)).video
    assert v is not None and v.fps == 30
    steps = np.diff(_frame_times(path))
    assert np.allclose(steps, 1 / 30, atol=1e-3)


async def test_preview_hlg_tone_mapped_to_bt709(samples_dir: Path, tmp_path: Path) -> None:
    caps = get_caps()
    if not (caps.has_filter("zscale") and caps.has_filter("tonemap")):
        pytest.skip("zscale/tonemap not available")
    path = await _preview(samples_dir / "clip_hlg.mp4", tmp_path)
    v = (await ffmpeg.probe(path)).video
    assert v is not None
    assert (v.color_transfer, v.color_primaries, v.color_space) == ("bt709",) * 3
    assert v.pix_fmt == "yuv420p" and not v.is_hdr and v.bit_depth in (None, 8)


async def test_preview_bakes_rotation(rotated_clip: Path, tmp_path: Path) -> None:
    src_probe = await ffmpeg.probe(rotated_clip)
    assert src_probe.video is not None and src_probe.video.rotation in (90, 270)
    path = await _preview(rotated_clip, tmp_path)
    v = (await ffmpeg.probe(path)).video
    assert v is not None and v.rotation == 0 and v.height > v.width  # portrait baked


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
