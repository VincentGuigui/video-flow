import asyncio
import shutil
import subprocess
import time
from fractions import Fraction
from pathlib import Path

import pytest

from videoflow.media import caps as caps_mod
from videoflow.media.ffmpeg import ProbeError, Progress, locate_binaries, probe, probe_caps, run

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")


def _ff(*args: str) -> None:
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-v", "error", "-y", *args], check=True, capture_output=True
    )


@pytest.fixture(scope="module")
def caps():
    return probe_caps()


def test_caps_ffmpeg_6_1(caps):
    assert caps.version_tuple >= (6, 1, 0)
    if caps.version_tuple < (7, 0, 0):
        assert caps.graph_flag == "-filter_complex_script"
    assert caps.graph_flag in ("-filter_complex_script", "-/filter_complex")
    assert {"fade", "wipeleft", "dissolve", "pixelize", "zoomin", "revealdown"} <= (
        caps.xfade_transitions
    )
    assert len(caps.xfade_transitions) >= 50
    assert caps.has_filter("xfade") and caps.has_filter("loudnorm")
    assert caps.has_encoder("libx264") and caps.has_encoder("aac")
    assert isinstance(caps.hwaccels, frozenset)


def test_parse_helpers():
    assert caps_mod.parse_version("ffmpeg version 6.1.1-3ubuntu5 Copyright")[1] == (6, 1, 1)
    assert caps_mod.parse_version("ffmpeg version n7.0 Copyright")[1] == (7, 0, 0)
    assert caps_mod.parse_version("ffmpeg version N-117000-gabc Copyright")[1] == (0, 0, 0)
    table = (
        "Filters:\n  T.. = x\n | = Source\n ... anull A->A  n\n"
        " .S. xfade   VV->V      Cross\n V....D libx264  H.264\n"
    )
    assert caps_mod.parse_table(table) == {"xfade", "anull", "libx264"}
    assert caps_mod.parse_hwaccels("Hardware acceleration methods:\ncuda\nvaapi\n") == {
        "cuda",
        "vaapi",
    }


def test_locate_binaries_override(tmp_path: Path):
    exe = shutil.which("ffmpeg")
    b = locate_binaries(ffmpeg=exe, tools_dir=tmp_path)
    assert b.ffmpeg == Path(exe)
    with pytest.raises(FileNotFoundError):
        locate_binaries(ffmpeg=tmp_path / "nope")


async def test_run_progress(tmp_path: Path):
    out = tmp_path / "o.mp4"
    seen: list[Progress] = []
    res = await run(
        ["-f", "lavfi", "-i", "testsrc2=s=320x180:r=25:d=2", "-c:v", "libx264", "-preset",
         "ultrafast", "-y", str(out)],
        on_progress=seen.append,
        duration_us=2_000_000,
    )  # fmt: skip
    assert res.ok and out.exists()
    assert seen and seen[-1].done and seen[-1].fraction == 1.0
    assert seen[-1].frame == 50
    assert abs(seen[-1].out_time_us - 2_000_000) < 100_000


async def test_run_failure_returns_stderr(tmp_path: Path):
    res = await run(["-i", str(tmp_path / "missing.mp4"), "-f", "null", "-"])
    assert not res.ok and res.returncode != 0 and "missing.mp4" in res.stderr_tail


async def test_cancel_within_one_second(tmp_path: Path):
    out = tmp_path / "o.mp4"
    cancel = asyncio.Event()
    seen: list[Progress] = []

    def on_progress(p: Progress) -> None:
        seen.append(p)
        if len(seen) == 1:
            cancel.set()

    t0 = time.monotonic()
    res = await run(
        ["-re", "-f", "lavfi", "-i", "testsrc2=s=320x180:r=25", "-c:v", "libx264",
         "-preset", "ultrafast", "-y", str(out)],
        on_progress=on_progress,
        cancel=cancel,
    )  # fmt: skip
    assert res.cancelled and not res.ok
    assert time.monotonic() - t0 < 5  # includes startup
    # time from cancel to return
    cancel2 = asyncio.Event()
    task = asyncio.create_task(
        run(
            ["-re", "-f", "lavfi", "-i", "testsrc2=s=320x180:r=25", "-f", "null", "-"],
            cancel=cancel2,
        )
    )
    await asyncio.sleep(1.0)
    t1 = time.monotonic()
    cancel2.set()
    r2 = await task
    assert r2.cancelled and time.monotonic() - t1 < 1.0


async def test_timeout():
    res = await run(
        ["-re", "-f", "lavfi", "-i", "testsrc2=s=64x64:r=25", "-f", "null", "-"], timeout=0.5
    )
    assert res.timed_out and not res.ok


async def test_probe_av_and_no_audio(tmp_path: Path):
    av = tmp_path / "av.mp4"
    _ff("-f", "lavfi", "-i", "testsrc2=s=320x180:r=30000/1001:d=1", "-f", "lavfi", "-i",
        "sine=r=44100:d=1", "-c:v", "libx264", "-c:a", "aac", "-ac", "1",
        "-metadata", "creation_time=2024-05-01T10:00:00Z", str(av))  # fmt: skip
    p = await probe(av)
    assert p.video and p.video.fps == Fraction(30000, 1001)
    assert not p.video.is_vfr and p.video.rotation == 0 and not p.video.is_hdr
    assert (p.video.width, p.video.height) == (320, 180)
    assert len(p.audio) == 1 and p.audio[0].sample_rate == 44100 and p.audio[0].channels == 1
    assert p.duration_us and abs(p.duration_us - 1_000_000) < 100_000
    assert p.creation_time is not None and p.creation_time.year == 2024

    silent = tmp_path / "silent.mp4"
    _ff("-f", "lavfi", "-i", "testsrc2=s=160x90:r=25:d=1", "-c:v", "libx264", str(silent))
    p2 = await probe(silent)
    assert p2.video and p2.audio == [] and not p2.has_audio


async def test_probe_rotation(tmp_path: Path):
    src = tmp_path / "src.mp4"
    _ff("-f", "lavfi", "-i", "testsrc2=s=320x180:r=25:d=1", "-c:v", "libx264", str(src))
    rot = tmp_path / "rot.mp4"
    _ff("-display_rotation", "90", "-i", str(src), "-c", "copy", str(rot))
    p = await probe(rot)
    assert p.video and p.video.rotation == 270
    assert p.video.display_size == (180, 320)


async def test_probe_vfr(tmp_path: Path):
    out = tmp_path / "vfr.mp4"
    _ff("-f", "lavfi", "-i", "testsrc2=s=160x90:r=25:d=6", "-vf",
        "select='not(mod(n,7))+gt(mod(n,50),40)'", "-fps_mode", "vfr", "-c:v", "libx264",
        str(out))  # fmt: skip
    p = await probe(out)
    assert p.video and p.video.is_vfr


async def test_probe_hdr(tmp_path: Path):
    out = tmp_path / "hlg.mp4"
    _ff("-f", "lavfi", "-i", "testsrc2=s=160x90:r=25:d=1", "-vf",
        "format=yuv420p10le,setparams=color_primaries=bt2020:color_trc=arib-std-b67"
        ":colorspace=bt2020nc",
        "-c:v", "libx265", "-x265-params", "log-level=none", str(out))  # fmt: skip
    p = await probe(out)
    assert p.video and p.video.is_hdr and p.video.color_transfer == "arib-std-b67"
    assert p.video.bit_depth == 10


async def test_probe_error(tmp_path: Path):
    with pytest.raises(ProbeError):
        await probe(tmp_path / "missing.mp4")
