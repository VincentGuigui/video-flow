"""Waveform peaks: one resolution, binary `.bin` of per-bucket min, max and RMS.

Layout (little endian): header `<4sHHII` = magic `VFPK`, version, peaks per second, analysis
sample rate, bucket count; then `count` records of int16 min, int16 max, uint16 rms (all scaled
by full scale). Audio is mixed to mono at 48 kHz before bucketing.
"""

from __future__ import annotations

import asyncio
import os
import struct
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from videoflow.media.caps import NO_WINDOW, locate_binaries
from videoflow.media.errors import MediaCancelled, MediaError

MAGIC = b"VFPK"
VERSION = 1
SAMPLE_RATE = 48_000
DEFAULT_PPS = 100
_HEADER = struct.Struct("<4sHHII")
_RECORD = np.dtype([("min", "<i2"), ("max", "<i2"), ("rms", "<u2")])
_READ_BYTES = 1 << 20


@dataclass(frozen=True)
class Peaks:
    peaks_per_second: int
    min: np.ndarray  # float32 in [-1, 1]
    max: np.ndarray
    rms: np.ndarray  # float32 in [0, 1]

    @property
    def count(self) -> int:
        return int(self.min.shape[0])


@dataclass(frozen=True)
class PeaksResult:
    path: Path
    cached: bool
    peaks_per_second: int
    count: int


def read_peaks(path: Path | str) -> Peaks:
    raw = Path(path).read_bytes()
    magic, version, pps, _sr, count = _HEADER.unpack_from(raw)
    if magic != MAGIC or version != VERSION:
        raise ValueError(f"not a v{VERSION} peaks file: {path}")
    rec = np.frombuffer(raw, dtype=_RECORD, count=count, offset=_HEADER.size)
    return Peaks(
        pps,
        rec["min"].astype(np.float32) / 32767,
        rec["max"].astype(np.float32) / 32767,
        rec["rms"].astype(np.float32) / 65535,
    )


def _bucketize(x: np.ndarray, bucket: int) -> np.ndarray:
    """Records for `x` (float32 mono); the last bucket may be shorter than `bucket`."""
    n = -(-x.shape[0] // bucket)
    rec = np.zeros(n, dtype=_RECORD)
    full = x.shape[0] // bucket
    if full:
        m = x[: full * bucket].reshape(full, bucket)
        rec["min"][:full] = np.rint(m.min(axis=1) * 32767)
        rec["max"][:full] = np.rint(m.max(axis=1) * 32767)
        rec["rms"][:full] = np.rint(np.minimum(np.sqrt((m * m).mean(axis=1)), 1.0) * 65535)
    if full < n:
        t = x[full * bucket :]
        rec["min"][full] = np.rint(t.min() * 32767)
        rec["max"][full] = np.rint(t.max() * 32767)
        rec["rms"][full] = np.rint(min(float(np.sqrt((t * t).mean())), 1.0) * 65535)
    return rec


def _kill(proc: asyncio.subprocess.Process) -> None:
    if proc.returncode is None:
        proc.kill()


async def compute_peaks(
    src: Path | str,
    out: Path | str,
    *,
    audio_index: int = 0,
    peaks_per_second: int = DEFAULT_PPS,
    cancel: asyncio.Event | None = None,
    ffmpeg: Path | str | None = None,
    force: bool = False,
) -> PeaksResult:
    """Write the peaks of audio stream `audio_index` of `src` to `out` (skipped when present)."""
    out = Path(out)
    if out.is_file() and not force:
        magic, _v, pps, _sr, count = _HEADER.unpack(out.read_bytes()[: _HEADER.size])
        if magic == MAGIC:
            return PeaksResult(out, True, pps, count)
    bucket = SAMPLE_RATE // peaks_per_second
    exe = str(ffmpeg) if ffmpeg else str(locate_binaries().ffmpeg)
    cmd = [
        exe, "-hide_banner", "-v", "error", "-nostdin", "-i", str(src),
        "-map", f"0:a:{audio_index}", "-vn", "-ac", "1", "-ar", str(SAMPLE_RATE),
        "-f", "f32le", "pipe:1",
    ]  # fmt: skip
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        creationflags=NO_WINDOW,
    )
    assert proc.stdout is not None and proc.stderr is not None
    stderr_task = asyncio.create_task(proc.stderr.read())
    cancel_task = asyncio.create_task(cancel.wait()) if cancel else None
    if cancel_task is not None:
        cancel_task.add_done_callback(lambda _t: _kill(proc))
    records: list[np.ndarray] = []
    pending = b""
    try:
        while chunk := await proc.stdout.read(_READ_BYTES):
            pending += chunk
            usable = (len(pending) // 4 // bucket) * bucket * 4
            if usable:
                records.append(_bucketize(np.frombuffer(pending[:usable], "<f4"), bucket))
                pending = pending[usable:]
        await proc.wait()
    except asyncio.CancelledError:
        if proc.returncode is None:
            proc.kill()
        raise
    finally:
        if cancel_task is not None:
            cancel_task.cancel()
    err = (await stderr_task).decode("utf-8", "replace")
    if cancel is not None and cancel.is_set():
        raise MediaCancelled("peaks cancelled")
    if proc.returncode != 0:
        raise MediaError(f"peaks extraction failed for {src}", err)
    tail = len(pending) // 4
    if tail:
        records.append(_bucketize(np.frombuffer(pending[: tail * 4], "<f4"), bucket))
    data = np.concatenate(records) if records else np.zeros(0, dtype=_RECORD)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(out.name + ".part")
    tmp.write_bytes(
        _HEADER.pack(MAGIC, VERSION, peaks_per_second, SAMPLE_RATE, len(data)) + data.tobytes()
    )
    os.replace(tmp, out)
    return PeaksResult(out, False, peaks_per_second, len(data))
