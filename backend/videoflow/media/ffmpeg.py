"""Async FFmpeg runner with -progress parsing and cancellation, plus ffprobe parsing."""

from __future__ import annotations

import asyncio
import json
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime
from fractions import Fraction
from pathlib import Path

from videoflow.media.caps import (
    NO_WINDOW,
    FFmpegCaps,
    get_caps,
    locate_binaries,
    probe_caps,
)

__all__ = [
    "AudioStreamInfo", "FFmpegCaps", "ProbeError", "ProbeResult", "Progress", "Result",
    "VideoStreamInfo", "get_caps", "locate_binaries", "probe", "probe_caps", "run",
]  # fmt: skip

CANCEL_Q_GRACE_S = 0.4
CANCEL_TERM_GRACE_S = 0.3
STDERR_TAIL_LINES = 200

HDR_TRANSFERS = frozenset({"smpte2084", "arib-std-b67"})


@dataclass(frozen=True)
class Progress:
    out_time_us: int = 0
    frame: int = 0
    fps: float = 0.0
    speed: float = 0.0
    total_size: int = 0
    done: bool = False
    fraction: float | None = None  # set when duration_us is known


@dataclass(frozen=True)
class Result:
    returncode: int
    cancelled: bool
    stderr_tail: str
    timed_out: bool = False

    @property
    def ok(self) -> bool:
        return self.returncode == 0 and not self.cancelled and not self.timed_out


ProgressCallback = Callable[[Progress], Awaitable[None] | None]


def _parse_progress_block(block: dict[str, str], duration_us: int | None) -> Progress:
    def num(key: str, default: float = 0) -> float:
        try:
            return float(block.get(key, default))
        except ValueError:
            return default

    # `out_time_us` is microseconds; older builds mislabel `out_time_ms` (also microseconds).
    raw = block.get("out_time_us", block.get("out_time_ms", "0"))
    try:
        out_us = max(int(raw), 0)
    except ValueError:
        out_us = 0
    speed_txt = block.get("speed", "").strip().rstrip("x")
    try:
        speed = float(speed_txt)
    except ValueError:
        speed = 0.0
    done = block.get("progress") == "end"
    fraction = None
    if duration_us:
        fraction = 1.0 if done else min(out_us / duration_us, 1.0)
    return Progress(
        out_time_us=out_us,
        frame=int(num("frame")),
        fps=num("fps"),
        speed=speed,
        total_size=int(num("total_size")),
        done=done,
        fraction=fraction,
    )


async def _emit(cb: ProgressCallback | None, p: Progress) -> None:
    if cb is None:
        return
    res = cb(p)
    if asyncio.iscoroutine(res) or isinstance(res, asyncio.Future):
        await res


async def _read_progress(
    stream: asyncio.StreamReader, cb: ProgressCallback | None, duration_us: int | None
) -> None:
    block: dict[str, str] = {}
    while line := await stream.readline():
        key, sep, value = line.decode("utf-8", "replace").strip().partition("=")
        if not sep:
            continue
        block[key] = value
        if key == "progress":
            await _emit(cb, _parse_progress_block(block, duration_us))
            block = {}


async def _read_tail(stream: asyncio.StreamReader, tail: deque[str]) -> None:
    while line := await stream.readline():
        tail.append(line.decode("utf-8", "replace").rstrip())


async def _stop(proc: asyncio.subprocess.Process) -> None:
    """Ask ffmpeg to quit (q on stdin), then terminate, then kill. Portable to Windows."""
    if proc.returncode is not None:
        return
    try:
        if proc.stdin is not None:
            proc.stdin.write(b"q\n")
            await proc.stdin.drain()
            proc.stdin.close()
    except (BrokenPipeError, ConnectionResetError, OSError):
        pass
    for action, grace in ((None, CANCEL_Q_GRACE_S), ("terminate", CANCEL_TERM_GRACE_S)):
        if action == "terminate" and proc.returncode is None:
            proc.terminate()
        try:
            await asyncio.wait_for(proc.wait(), grace)
            return
        except TimeoutError:
            continue
    if proc.returncode is None:
        proc.kill()
        await proc.wait()


async def run(
    args: list[str],
    *,
    on_progress: ProgressCallback | None = None,
    cancel: asyncio.Event | None = None,
    duration_us: int | None = None,
    ffmpeg: Path | str | None = None,
    timeout: float | None = None,  # noqa: ASYNC109
) -> Result:
    """Run ffmpeg with `args` (without the binary). Progress comes from `-progress pipe:1`.

    Setting `cancel` stops ffmpeg (q, then terminate, then kill) and returns `cancelled=True`.
    """
    exe = str(ffmpeg) if ffmpeg else str(locate_binaries().ffmpeg)
    cmd = [exe, "-hide_banner", "-nostats", "-progress", "pipe:1", *args]
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        creationflags=NO_WINDOW,
    )
    assert proc.stdout is not None and proc.stderr is not None
    tail: deque[str] = deque(maxlen=STDERR_TAIL_LINES)
    readers = [
        asyncio.create_task(_read_progress(proc.stdout, on_progress, duration_us)),
        asyncio.create_task(_read_tail(proc.stderr, tail)),
    ]
    waiter = asyncio.create_task(proc.wait())
    cancel_task = asyncio.create_task(cancel.wait()) if cancel else None
    watch: set[asyncio.Task[object]] = {waiter, *([cancel_task] if cancel_task else [])}
    cancelled = timed_out = False
    try:
        await asyncio.wait(watch, timeout=timeout, return_when=asyncio.FIRST_COMPLETED)
        if not waiter.done():
            if cancel is not None and cancel.is_set():
                cancelled = True
            else:
                timed_out = True
            await _stop(proc)
        await asyncio.gather(*readers, return_exceptions=True)
    except asyncio.CancelledError:
        await asyncio.shield(_stop(proc))
        raise
    finally:
        for t in (waiter, cancel_task, *readers):
            if t is not None and not t.done():
                t.cancel()
    return Result(
        returncode=proc.returncode if proc.returncode is not None else -1,
        cancelled=cancelled,
        stderr_tail="\n".join(tail),
        timed_out=timed_out,
    )


# ---------------------------------------------------------------- ffprobe


class ProbeError(RuntimeError):
    pass


@dataclass(frozen=True)
class VideoStreamInfo:
    index: int
    codec: str
    width: int  # coded size
    height: int
    fps: Fraction  # average frame rate
    r_fps: Fraction  # container "real base" rate
    is_vfr: bool
    rotation: int  # clockwise degrees to apply for upright display: 0, 90, 180, 270
    pix_fmt: str
    color_transfer: str | None
    color_primaries: str | None
    color_space: str | None
    is_hdr: bool
    bit_depth: int | None
    nb_frames: int | None
    duration_us: int | None

    @property
    def display_size(self) -> tuple[int, int]:
        return (
            (self.height, self.width) if self.rotation in (90, 270) else (self.width, self.height)
        )


@dataclass(frozen=True)
class AudioStreamInfo:
    index: int
    codec: str
    sample_rate: int
    channels: int
    channel_layout: str | None
    duration_us: int | None
    language: str | None


@dataclass(frozen=True)
class ProbeResult:
    path: Path
    format_name: str
    duration_us: int | None
    size_bytes: int | None
    bit_rate: int | None
    creation_time: datetime | None
    video: VideoStreamInfo | None
    audio: list[AudioStreamInfo] = field(default_factory=list)

    @property
    def has_audio(self) -> bool:
        return bool(self.audio)


def _fraction(text: str | None) -> Fraction:
    if not text or text in ("0/0", "N/A"):
        return Fraction(0)
    try:
        return Fraction(text)
    except (ValueError, ZeroDivisionError):
        return Fraction(0)


def _seconds_to_us(text: object) -> int | None:
    try:
        return round(float(text) * 1_000_000)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _int(text: object) -> int | None:
    try:
        return int(text)  # type: ignore[call-overload,no-any-return]
    except (TypeError, ValueError):
        return None


def _parse_time(text: str | None) -> datetime | None:
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _rotation(stream: dict[str, object]) -> int:
    raw: object = None
    for sd in stream.get("side_data_list", []) or []:  # type: ignore[attr-defined]
        if isinstance(sd, dict) and "rotation" in sd:
            raw = sd["rotation"]
            break
    if raw is None:
        tags = stream.get("tags")
        raw = tags.get("rotate") if isinstance(tags, dict) else None
    try:
        ccw = round(float(raw))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0
    return (-ccw) % 360


def _is_vfr(avg: Fraction, real: Fraction) -> bool:
    if avg <= 0 or real <= 0:
        return False
    return abs(avg - real) / real > Fraction(1, 100)


def _video(s: dict[str, object]) -> VideoStreamInfo:
    avg, real = _fraction(s.get("avg_frame_rate")), _fraction(s.get("r_frame_rate"))  # type: ignore[arg-type]
    trc = s.get("color_transfer")
    bits = _int(s.get("bits_per_raw_sample"))
    pix = str(s.get("pix_fmt", ""))
    if bits is None and ("10le" in pix or "10be" in pix or "p010" in pix):
        bits = 10
    return VideoStreamInfo(
        index=int(s["index"]),  # type: ignore[call-overload]
        codec=str(s.get("codec_name", "")),
        width=int(s.get("width", 0)),  # type: ignore[call-overload]
        height=int(s.get("height", 0)),  # type: ignore[call-overload]
        fps=avg or real,
        r_fps=real,
        is_vfr=_is_vfr(avg, real),
        rotation=_rotation(s),
        pix_fmt=pix,
        color_transfer=str(trc) if trc else None,
        color_primaries=str(s["color_primaries"]) if s.get("color_primaries") else None,
        color_space=str(s["color_space"]) if s.get("color_space") else None,
        is_hdr=trc in HDR_TRANSFERS,
        bit_depth=bits,
        nb_frames=_int(s.get("nb_frames")),
        duration_us=_seconds_to_us(s.get("duration")),
    )


def _audio(s: dict[str, object]) -> AudioStreamInfo:
    tags = s.get("tags")
    lang = tags.get("language") if isinstance(tags, dict) else None
    return AudioStreamInfo(
        index=int(s["index"]),  # type: ignore[call-overload]
        codec=str(s.get("codec_name", "")),
        sample_rate=_int(s.get("sample_rate")) or 0,
        channels=_int(s.get("channels")) or 0,
        channel_layout=str(s["channel_layout"]) if s.get("channel_layout") else None,
        duration_us=_seconds_to_us(s.get("duration")),
        language=lang if lang and lang != "und" else None,
    )


def parse_probe(path: Path, data: dict[str, object]) -> ProbeResult:
    fmt: dict[str, object] = data.get("format", {})  # type: ignore[assignment]
    streams: list[dict[str, object]] = data.get("streams", [])  # type: ignore[assignment]
    video = None
    for s in streams:
        if s.get("codec_type") == "video" and not (s.get("disposition") or {}).get(  # type: ignore[attr-defined]
            "attached_pic"
        ):
            video = _video(s)
            break
    tags = fmt.get("tags")
    created = None
    if isinstance(tags, dict):
        created = _parse_time(tags.get("creation_time"))
    if created is None and video is not None:
        for s in streams:
            st = s.get("tags")
            if s.get("index") == video.index and isinstance(st, dict):
                created = _parse_time(st.get("creation_time"))
    return ProbeResult(
        path=path,
        format_name=str(fmt.get("format_name", "")),
        duration_us=_seconds_to_us(fmt.get("duration")),
        size_bytes=_int(fmt.get("size")),
        bit_rate=_int(fmt.get("bit_rate")),
        creation_time=created,
        video=video,
        audio=[_audio(s) for s in streams if s.get("codec_type") == "audio"],
    )


async def probe(path: Path | str, ffprobe: Path | str | None = None) -> ProbeResult:
    """Run ffprobe on `path` and return a typed result. Raises ProbeError on failure."""
    exe = str(ffprobe) if ffprobe else str(locate_binaries().ffprobe)
    proc = await asyncio.create_subprocess_exec(
        exe, "-v", "error", "-print_format", "json", "-show_format", "-show_streams",
        str(path),
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        creationflags=NO_WINDOW,
    )  # fmt: skip
    out, err = await proc.communicate()
    if proc.returncode != 0:
        raise ProbeError(f"ffprobe failed for {path}: {err.decode('utf-8', 'replace').strip()}")
    try:
        data = json.loads(out)
    except json.JSONDecodeError as exc:
        raise ProbeError(f"ffprobe returned invalid JSON for {path}") from exc
    return parse_probe(Path(path), data)
