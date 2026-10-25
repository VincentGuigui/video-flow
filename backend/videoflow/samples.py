"""Deterministic synthetic rushes (FFmpeg lavfi + flite TTS) with a ground-truth manifest.

Everything is generated from fixed seeds, so the same generator source and FFmpeg build
give the same files. `generator_hash()` keys caches. Entry point: `generate(out_dir)`.
"""

from __future__ import annotations

import functools
import hashlib
import json
import os
import shutil
import subprocess
import sys
import wave
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any

import numpy as np

from videoflow.media.caps import NO_WINDOW, locate_binaries

MANIFEST_NAME = "manifest.json"
MANIFEST_VERSION = 1
SR = 48000
SYNC_LAG_S = 3.217
GAP_S = 1.0
VOICE = "kal16"


# Retake scripts: flite only ships English voices, so the French script is read with the
# same voice (accented pronunciation, but stable timing and plain-text ground truth).
SCRIPTS: dict[str, dict[str, str]] = {
    "fr": {
        "false_start": "alors dans la... attends je reprends",
        "take": "aujourd'hui nous allons assembler la video a partir des rushes",
    },
    "en": {
        "false_start": "so in the... wait let me start over",
        "take": "today we are going to assemble the video from the rushes",
    },
}
_CAM_B_VIDEO = (
    "gradients=size=640x360:rate=25:c0=0x802020:c1=0x2060a0:c2=0xc0c040:nb_colors=3:"
    "speed=0.02:seed=3"
)
SYNC_SENTENCES = (
    "the quick brown fox jumps over the lazy dog",
    "pack my box with five dozen liquor jugs",
)


def generator_hash() -> str:
    """Hash of this module's source plus the FFmpeg version (files depend on both)."""
    h = hashlib.sha256(Path(__file__).read_bytes())
    try:
        out = subprocess.run(
            [str(locate_binaries().ffmpeg), "-version"],
            capture_output=True, text=True, check=True, creationflags=NO_WINDOW,
        ).stdout.splitlines()[0]  # fmt: skip
    except (OSError, subprocess.CalledProcessError, FileNotFoundError):
        out = "no-ffmpeg"
    h.update(out.encode())
    return h.hexdigest()[:16]


def default_cache_dir() -> Path:
    """Per-user cache root for generated samples (VIDEOFLOW_SAMPLES_CACHE overrides)."""
    env = os.environ.get("VIDEOFLOW_SAMPLES_CACHE")
    if env:
        return Path(env)
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        base = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    return base / "videoflow" / "samples"


def ensure_samples(cache_root: Path | None = None) -> Path:
    """Return the samples directory for the current generator hash, generating if missing."""
    root = cache_root or default_cache_dir()
    final = root / generator_hash()
    if (final / MANIFEST_NAME).is_file():
        return final
    root.mkdir(parents=True, exist_ok=True)
    tmp = root / f"{final.name}.tmp-{os.getpid()}"
    shutil.rmtree(tmp, ignore_errors=True)
    generate(tmp)
    try:
        tmp.rename(final)
    except OSError:  # another process won the race
        shutil.rmtree(tmp, ignore_errors=True)
        if not (final / MANIFEST_NAME).is_file():
            raise
    return final


# --------------------------------------------------------------------------- helpers


_Arg = str | Path | int | float


def _run(args: Sequence[_Arg]) -> None:
    exe = str(locate_binaries().ffmpeg)
    cmd = [exe, "-hide_banner", "-loglevel", "error", "-nostdin", "-y", *map(str, args)]
    proc = subprocess.run(cmd, capture_output=True, text=True, creationflags=NO_WINDOW)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg failed ({proc.stderr.strip()}): {' '.join(cmd)}")


_DET = ["-fflags", "+bitexact", "-flags:v", "+bitexact", "-flags:a", "+bitexact",
        "-map_metadata", "-1"]  # fmt: skip
_V264 = ["-c:v", "libx264", "-preset", "ultrafast", "-crf", "30", "-threads", "1", "-g", "50"]
_AAC = ["-c:a", "aac", "-b:a", "64k"]


def _write_wav(path: Path, samples: np.ndarray) -> None:
    pcm = np.clip(samples, -1.0, 1.0)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((pcm * 32767).astype("<i2").tobytes())


def _read_wav(path: Path) -> np.ndarray:
    with wave.open(str(path), "rb") as w:
        raw = w.readframes(w.getnframes())
    return np.frombuffer(raw, dtype="<i2").astype(np.float64) / 32768.0


def _tts(text: str, path: Path) -> np.ndarray:
    """Synthesize `text` with flite, trimmed to the speech (20 ms margin)."""
    _run(["-f", "lavfi", "-i", f"flite=text='{text}':voice={VOICE}",
          "-ar", SR, "-ac", 1, "-c:a", "pcm_s16le", path])  # fmt: skip
    x = _read_wav(path)
    idx = np.flatnonzero(np.abs(x) > 0.01)
    pad = int(0.02 * SR)
    return x[max(idx[0] - pad, 0) : idx[-1] + pad + 1]


def _silence(seconds: float) -> np.ndarray:
    return np.zeros(round(seconds * SR))


def _frames_for(seconds: float, fps: Fraction) -> int:
    return -int(-(Fraction(seconds).limit_denominator(100000) * fps) // 1)


@dataclass
class _Clip:
    """A file to produce plus its expected properties (ground truth for tests)."""

    name: str
    width: int
    height: int
    fps: Fraction
    frames: int
    audio_channels: int
    vfr: bool = False
    color_trc: str | None = None
    note: str = ""
    duration_s: float | None = None  # override when timestamps are irregular (VFR)

    def manifest(self) -> dict[str, Any]:
        return {
            "path": self.name,
            "width": self.width,
            "height": self.height,
            "fps": f"{self.fps.numerator}/{self.fps.denominator}",
            "frames": self.frames,
            "duration_s": self.duration_s or float(Fraction(self.frames) / self.fps),
            "audio_channels": self.audio_channels,
            "audio_sample_rate": SR if self.audio_channels else None,
            "vfr": self.vfr,
            "color_trc": self.color_trc,
            "note": self.note,
        }


def _fps_str(f: Fraction) -> str:
    return f"{f.numerator}/{f.denominator}"


def _speech_video(out: Path, wav: Path, clip: _Clip, vsrc: str, *, af: str | None = None) -> None:
    args: list[_Arg] = [
        "-f", "lavfi", "-i", f"{vsrc}=size={clip.width}x{clip.height}:rate={_fps_str(clip.fps)}",
        "-i", wav,
    ]  # fmt: skip
    if af:
        args += ["-af", af]
    args += ["-frames:v", clip.frames, "-t", float(Fraction(clip.frames) / clip.fps),
             "-pix_fmt", "yuv420p", *_V264, *_AAC, *_DET, out]  # fmt: skip
    _run(args)


# --------------------------------------------------------------------------- generator


def generate(out_dir: Path, progress: Callable[[str], None] | None = None) -> dict[str, Any]:
    """Generate all samples into `out_dir` and write manifest.json. Returns the manifest."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    work = out_dir / "_work"
    work.mkdir(exist_ok=True)
    say = progress or (lambda _m: None)

    # Stage 1: TTS (parallel).
    jobs: dict[str, str] = {
        f"{lang}_{kind}": text for lang, d in SCRIPTS.items() for kind, text in d.items()
    }
    for i, s in enumerate(SYNC_SENTENCES):
        jobs[f"sync_{i}"] = s
    with ThreadPoolExecutor(max_workers=4) as ex:
        futs = {k: ex.submit(_tts, t, work / f"tts_{k}.wav") for k, t in jobs.items()}
        speech = {k: f.result() for k, f in futs.items()}
    say("tts done")

    manifest: dict[str, Any] = {
        "version": MANIFEST_VERSION,
        "generator_hash": generator_hash(),
        "files": {},
        "retake_scripts": {},
        "sync": {},
        "near_duplicate_groups": [],
        "different_shots": [],
        "cuts": {},
        "silent_files": [],
    }
    clips: list[_Clip] = []
    tasks: list[Callable[[], None]] = []

    def add(clip: _Clip, task: Callable[[], None]) -> _Clip:
        clips.append(clip)
        tasks.append(task)
        return clip

    # Retake scripts (video 640x360p25 + mono speech with exact utterance times).
    fps25 = Fraction(25)
    for lang, d in SCRIPTS.items():
        t = 0.5
        parts = [_silence(t)]
        utts: list[dict[str, Any]] = []
        seq = [("false_start", d["false_start"])] + [("take", d["take"])] * 3
        n_take = 0
        for kind, text in seq:
            x = speech[f"{lang}_{kind}"]
            dur = len(x) / SR
            if kind == "take":
                n_take += 1
            utts.append({
                "id": f"{lang}-fs" if kind == "false_start" else f"{lang}-t{n_take}",
                "kind": kind, "text": text,
                "start_s": round(t, 4), "end_s": round(t + dur, 4),
            })  # fmt: skip
            parts += [x, _silence(GAP_S)]
            t += dur + GAP_S
        audio = np.concatenate(parts[:-1] + [_silence(0.5)])
        frames = _frames_for(len(audio) / SR, fps25)
        audio = np.pad(audio, (0, round(frames / 25 * SR) - len(audio)))
        wav = work / f"retake_{lang}.wav"
        _write_wav(wav, audio)
        name = f"retake_{lang}.mp4"
        clip = _Clip(name, 640, 360, fps25, frames, 1, note=f"retake script ({lang})")
        add(clip, functools.partial(_speech_video, out_dir / clip.name, wav, clip, "testsrc2"))
        takes = [u["id"] for u in utts if u["kind"] == "take"]
        manifest["retake_scripts"][lang] = {
            "file": name,
            "language": lang,
            "voice": VOICE,
            "gap_s": GAP_S,
            "utterances": utts,
            "false_start_ids": [u["id"] for u in utts if u["kind"] == "false_start"],
            "retake_groups": [takes],
            "expected_beats": [{"text": d["take"], "take_ids": takes, "best": takes[-1]}],
        }

    # Sync reference (720p25 stereo) and delayed, filtered B camera.
    rng = np.random.default_rng(1234)
    click = rng.standard_normal(int(0.05 * SR)) * np.hanning(int(0.05 * SR)) * 0.8
    ref = np.concatenate([
        _silence(0.8), click, _silence(0.7), speech["sync_0"], _silence(0.8),
        speech["sync_1"], _silence(0.6),
    ])  # fmt: skip
    a_frames = _frames_for(len(ref) / SR, fps25)
    ref = np.pad(ref, (0, round(a_frames / 25 * SR) - len(ref)))
    ref_wav = work / "sync_ref.wav"
    _write_wav(ref_wav, ref * 0.9)
    clip_a = _Clip("cam_a_720p25_stereo.mp4", 1280, 720, fps25, a_frames, 2,
                   note="sync reference (camera A)")  # fmt: skip
    add(clip_a, lambda: _speech_video(
        out_dir / clip_a.name, ref_wav, clip_a, "testsrc2", af="pan=stereo|c0=c0|c1=0.8*c0"
    ))  # fmt: skip
    b_frames = _frames_for(len(ref) / SR + SYNC_LAG_S, fps25)
    clip_b = _Clip(
        "cam_b_delayed_mono.mp4",
        640,
        360,
        fps25,
        b_frames,
        1,
        note="camera B: A's audio delayed 3.217 s, band-limited, with noise",
    )

    def make_b() -> None:
        delay_ms = round(SYNC_LAG_S * 1000)
        fc = (
            f"[1:a]adelay={delay_ms}:all=1,highpass=f=150,lowpass=f=3400,volume=0.5[d];"
            "[2:a]volume=1[n];[d][n]amix=inputs=2:duration=first:normalize=0,apad[a]"
        )
        _run(["-f", "lavfi", "-i", _CAM_B_VIDEO,
              "-i", ref_wav,
              "-f", "lavfi", "-i", f"anoisesrc=a=0.004:r={SR}:seed=1:c=pink",
              "-filter_complex", fc, "-map", "0:v", "-map", "[a]", "-ac", 1, "-ar", SR,
              "-frames:v", b_frames, "-t", b_frames / 25,
              "-pix_fmt", "yuv420p", *_V264, *_AAC, *_DET,
              out_dir / clip_b.name])  # fmt: skip

    add(clip_b, make_b)
    manifest["sync"] = {
        "reference": clip_a.name,
        "other": clip_b.name,
        "lag_s": SYNC_LAG_S,
        "convention": "an event at time t in the reference occurs at t + lag_s in other",
        "click_at_s": 0.8,
    }

    # Other format variants.
    def tone(freq: int) -> str:
        return f"sine=frequency={freq}:sample_rate={SR}"

    def av(clip: _Clip, vsrc: str, *, extra_v: list[str | Path] | None = None,
           pix: str = "yuv420p", venc: list[str] | None = None, vf: str | None = None,
           ) -> Callable[[], None]:  # fmt: skip
        def run() -> None:
            args: list[_Arg] = ["-f", "lavfi", "-i", vsrc]
            if clip.audio_channels:
                args += ["-f", "lavfi", "-i", tone(440)]
            if vf:
                args += ["-vf", vf]
            args += ["-frames:v", clip.frames, "-pix_fmt", pix, *(venc or _V264)]
            args += extra_v or []
            if clip.audio_channels:
                # -frames:v with -shortest can leave a scheduler-dependent audio tail
                # on FFmpeg 7. Bound output time explicitly, including the VFR sample.
                duration = clip.duration_s or float(Fraction(clip.frames) / clip.fps)
                args += ["-ac", clip.audio_channels, *_AAC, "-t", duration]
            else:
                args += ["-an"]
            _run([*args, *_DET, out_dir / clip.name])

        return run  # noqa: B023

    f2997 = Fraction(30000, 1001)
    c = add(_Clip("clip_480p2997_mono.mp4", 854, 480, f2997, 120, 1), lambda: None)
    tasks[-1] = av(c, f"testsrc2=size=854x480:rate=30000/1001")  # noqa: F541
    c = add(_Clip("clip_vertical_1080x1920_24_noaudio.mp4", 1080, 1920, Fraction(24), 72, 0),
            lambda: None)  # fmt: skip
    tasks[-1] = av(c, "testsrc2=size=1080x1920:rate=24")
    c = add(_Clip("clip_vfr.mp4", 640, 360, Fraction(30), 0, 1, vfr=True,
                  note="variable frame rate: 7 of every 10 source frames kept"),
            lambda: None)  # fmt: skip
    # 120 source frames -> frames with n%10 < 7 -> 84 frames kept.
    c.frames = 84
    c.duration_s = 3.9  # last kept frame n=116 -> 116/30 + 1/30
    tasks[-1] = av(
        c,
        "testsrc2=size=640x360:rate=30:duration=4",
        vf="select='lt(mod(n,10),7)'",
        extra_v=["-fps_mode", "passthrough", "-video_track_timescale", "90000"],
    )
    c = add(_Clip("clip_hlg.mp4", 1280, 720, fps25, 75, 2, color_trc="arib-std-b67",
                  note="HLG, BT.2020, 10-bit"), lambda: None)  # fmt: skip
    tasks[-1] = av(c, "testsrc2=size=1280x720:rate=25", pix="yuv420p10le",
                   extra_v=["-color_primaries", "bt2020", "-color_trc", "arib-std-b67",
                            "-colorspace", "bt2020nc", "-color_range", "tv",
                            "-x264-params",
                            "colorprim=bt2020:transfer=arib-std-b67:"
                            "colormatrix=bt2020nc"])  # fmt: skip

    # Silent clip: real audio stream carrying digital silence.
    c = add(_Clip("clip_silent.mp4", 640, 360, fps25, 75, 2, note="video with silent audio"),
            lambda: None)  # fmt: skip

    def make_silent() -> None:
        _run(["-f", "lavfi", "-i", "smptebars=size=640x360:rate=25",
              "-f", "lavfi", "-i", f"anullsrc=channel_layout=stereo:sample_rate={SR}",
              "-frames:v", 75, "-t", 3, "-pix_fmt", "yuv420p", *_V264, *_AAC, *_DET,
              out_dir / "clip_silent.mp4"])  # fmt: skip

    tasks[-1] = make_silent
    manifest["silent_files"].append(c.name)

    # B-roll: two near-duplicate shots and one different, all silent.
    fps24 = Fraction(24)
    shot_a = (
        "gradients=size=640x360:rate=24:c0=0x205030:c1=0xd0a060:c2=0x303080:"
        "nb_colors=3:speed=0.01:seed=7"
    )
    broll = [
        ("broll_a1.mp4", shot_a, None),
        ("broll_a2.mp4", shot_a, "eq=brightness=0.02,noise=all_seed=5:all_strength=2:allf=t"),
        ("broll_b.mp4", "mandelbrot=size=640x360:rate=24", None),
    ]
    for name, src, vf in broll:
        c = add(_Clip(name, 640, 360, fps24, 72, 0, note="silent B-roll"), lambda: None)
        tasks[-1] = av(c, src, vf=vf)
        manifest["silent_files"].append(name)
    manifest["near_duplicate_groups"] = [["broll_a1.mp4", "broll_a2.mp4"]]
    manifest["different_shots"] = [["broll_a1.mp4", "broll_b.mp4"]]

    # Montage with hard cuts at known times (shot detection ground truth).
    seg = 36  # frames per shot at 24 fps (1.5 s)
    c = add(_Clip("montage_cuts.mp4", 640, 360, fps24, seg * 4, 0, note="4 shots, 3 hard cuts"),
            lambda: None)  # fmt: skip

    def make_montage() -> None:
        srcs = ["testsrc2=size=640x360:rate=24", "mandelbrot=size=640x360:rate=24",
                "smptebars=size=640x360:rate=24", shot_a]  # fmt: skip
        args: list[_Arg] = []
        for s in srcs:
            args += ["-f", "lavfi", "-i", s]
        fc = "".join(f"[{i}:v]trim=end_frame={seg},setpts=PTS-STARTPTS[v{i}];" for i in range(4))
        fc += "".join(f"[v{i}]" for i in range(4)) + "concat=n=4:v=1:a=0[v]"
        _run(
            [
                *args,
                "-filter_complex",
                fc,
                "-map",
                "[v]",
                "-r",
                "24",
                "-fps_mode",
                "cfr",
                "-frames:v",
                seg * 4,
                "-pix_fmt",
                "yuv420p",
                *_V264,
                "-an",
                *_DET,
                out_dir / "montage_cuts.mp4",
            ]
        )

    tasks[-1] = make_montage
    manifest["cuts"] = {"file": c.name, "cut_times_s": [i * seg / 24 for i in (1, 2, 3)]}

    # Stage 2: encode everything (parallel, one thread per x264 job).
    with ThreadPoolExecutor(max_workers=os.cpu_count() or 4) as ex:
        for f in [ex.submit(t) for t in tasks]:
            f.result()
    say("encode done")

    manifest["files"] = {c.name: c.manifest() for c in clips}
    shutil.rmtree(work, ignore_errors=True)
    (out_dir / MANIFEST_NAME).write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return manifest


def main(argv: Sequence[str] | None = None) -> int:
    import argparse
    import time

    p = argparse.ArgumentParser(description="Generate deterministic synthetic sample rushes.")
    p.add_argument("out", nargs="?", type=Path, default=Path("samples"))
    args = p.parse_args(argv)
    t0 = time.monotonic()
    generate(args.out, progress=lambda m: print(m, flush=True))
    print(f"wrote {args.out} in {time.monotonic() - t0:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
