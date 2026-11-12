"""Preview media in two stages (docs/features/import-analysis/importing.md#preview-media).

1. **Quick pass**, run by the import (about one second per minute of footage): one still
   per second, taken from keyframes only (no full decode), and the sound in Opus. The
   editor is usable at once: the preview shows the still of the current second and plays
   the real sound.
2. **Background video**: one VP9/Opus WebM per source (540p, a keyframe every second),
   made directly from the original in a single low-priority queue, one file at a time.
   As soon as it is ready the editor uses it, and the stills and the sound are deleted.

WebM plays in Qt WebEngine (which has no H.264 or AAC) and in browsers alike. Originals
are never modified; everything lives in the project's rebuildable cache.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import os
import shutil
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from videoflow.media import ffmpeg
from videoflow.media.caps import get_caps
from videoflow.media.proxy import proxy_fps, proxy_size, video_filter
from videoflow.project.models import Asset
from videoflow.project.store import Bundle

VERSION = 2
VIDEO_HEIGHT = 540
STILL_HEIGHT = 360
STILL_PATTERN = "f_%05d.jpg"
Progress = Callable[[float], None]
PLAYABLE_AUDIO = frozenset({".wav", ".mp3", ".flac", ".ogg", ".oga", ".opus"})
"""Audio-only formats Qt WebEngine and browsers play directly: no preview is made."""


def plays_as_is(asset: Asset) -> bool:
    """Image, or audio-only source in a format the editor plays without conversion."""
    return asset.probe.still or (
        asset.probe.video is None and Path(asset.path).suffix.casefold() in PLAYABLE_AUDIO
    )


def _key(asset: Asset) -> str:
    return hashlib.sha256(f"{asset.content_hash}:preview-v{VERSION}".encode()).hexdigest()[:24]


def _legacy_key(asset: Asset) -> str:
    """WebM files of earlier versions (made from the H.264 proxy) are still used."""
    return hashlib.sha256((asset.content_hash + ":webm-v1").encode()).hexdigest()[:24]


def encoder_threads() -> int:
    """Half the processors at most, so editing stays fluid while previews are made."""
    return max(1, (os.cpu_count() or 2) // 2)


@dataclass
class Status:
    video: bool
    audio: bool
    stills: int
    state: str
    """`ready` (video, or audio-only/image source), `stills` (quick pass done, video queued
    or encoding), `pending` (nothing yet), `failed`."""
    progress: float | None = None
    error: str | None = None

    def dump(self) -> dict[str, Any]:
        return {
            "video": self.video,
            "audio": self.audio,
            "stills": self.stills,
            "state": self.state,
            "progress": self.progress,
            "error": self.error,
        }


class Previews:
    def __init__(self, bundle: Bundle) -> None:
        self.bundle = bundle
        self.queue: list[str] = []
        self.wake = asyncio.Event()
        self.task: asyncio.Task[None] | None = None
        self.current: str | None = None
        self.progress: dict[str, float] = {}
        self.errors: dict[str, str] = {}
        self.locks: dict[str, asyncio.Lock] = {}
        self.cancel = asyncio.Event()

    # Files ---------------------------------------------------------------------------

    def video_path(self, asset: Asset) -> Path | None:
        """The finished preview video of a source, if any."""
        for path in (
            self.bundle.proxies_dir / f"{_key(asset)}.webm",
            self.bundle.proxies_dir / f"{_legacy_key(asset)}.webm",
        ):
            if path.is_file():
                return path
        return None

    def folder(self, asset: Asset) -> Path:
        return self.bundle.previews_dir / _key(asset)

    def audio_path(self, asset: Asset) -> Path | None:
        path = self.folder(asset) / "audio.webm"
        return path if path.is_file() else None

    def still_count(self, asset: Asset) -> int:
        folder = self.folder(asset)
        return sum(1 for _ in folder.glob("f_*.jpg")) if folder.is_dir() else 0

    def still_path(self, asset: Asset, index: int) -> Path | None:
        """Still of second `index` (0-based); the last one for times past the end."""
        count = self.still_count(asset)
        if count == 0:
            return None
        number = min(max(0, index), count - 1) + 1
        path = self.folder(asset) / (STILL_PATTERN % number)
        return path if path.is_file() else None

    def status(self, asset: Asset) -> Status:
        if plays_as_is(asset):
            return Status(video=asset.probe.still, audio=False, stills=0, state="ready")
        video = self.video_path(asset) is not None
        audio = self.audio_path(asset) is not None
        stills = 0 if video else self.still_count(asset)
        if video or (asset.probe.video is None and audio):
            state = "ready"
        elif asset.id in self.errors:
            state = "failed"
        elif stills or audio:
            state = "stills"
        else:
            state = "pending"
        return Status(
            video=video,
            audio=audio and not video,
            stills=stills,
            state=state,
            progress=self.progress.get(asset.id) if asset.id == self.current else None,
            error=self.errors.get(asset.id),
        )

    # Quick pass ----------------------------------------------------------------------

    async def quick(self, asset: Asset, source: Path, on_progress: Progress | None = None) -> None:
        """Stills (one per second, keyframes only) and the sound, in one FFmpeg run."""
        if plays_as_is(asset) or self.video_path(asset) is not None:
            return
        async with self.locks.setdefault(asset.id, asyncio.Lock()):
            folder = self.folder(asset)
            if self.still_count(asset) or self.audio_path(asset):
                return
            temp = folder.with_name(f".{folder.name}-{uuid.uuid4().hex}")
            temp.mkdir(parents=True, exist_ok=True)
            args = ["-y", "-nostdin"]
            if asset.probe.video:
                args += ["-skip_frame", "nokey"]
            args += ["-i", str(source)]
            if asset.probe.video:
                args += [
                    "-map", "0:v:0", "-an", "-sn", "-dn",
                    "-vf", f"fps=1:start_time=0,scale=-2:'min({STILL_HEIGHT},ih)'",
                    "-q:v", "5", str(temp / STILL_PATTERN),
                ]  # fmt: skip
            if asset.probe.has_audio:
                args += [
                    "-map", "0:a:0", "-vn", "-sn", "-dn",
                    "-c:a", "libopus", "-b:a", "96k", "-ac", "2", "-ar", "48000",
                    str(temp / "audio.webm"),
                ]  # fmt: skip

            def progress(p: ffmpeg.Progress) -> None:
                if on_progress and p.fraction is not None:
                    on_progress(p.fraction)

            try:
                result = await ffmpeg.run(
                    args, on_progress=progress, duration_us=asset.probe.duration_us or None
                )
                if not result.ok:
                    raise ValueError(f"Preview stills failed: {result.stderr_tail}")
                shutil.rmtree(folder, ignore_errors=True)
                os.replace(temp, folder)
            finally:
                shutil.rmtree(temp, ignore_errors=True)

    # Background video ----------------------------------------------------------------

    def enqueue(self, asset_ids: list[str], *, first: bool = False) -> None:
        """Queue sources whose preview video is missing; `first` moves them to the front."""
        for asset_id in reversed(asset_ids) if first else asset_ids:
            asset = self.bundle.project.asset(asset_id)
            if asset is None or plays_as_is(asset) or self.video_path(asset) is not None:
                continue
            if asset.probe.video is None and self.audio_path(asset) is not None:
                continue
            if asset_id == self.current:
                continue
            if asset_id in self.queue:
                if not first:
                    continue
                self.queue.remove(asset_id)
            if first:
                self.queue.insert(0, asset_id)
            else:
                self.queue.append(asset_id)
            self.errors.pop(asset_id, None)
        if self.queue:
            self.wake.set()
            if self.task is None or self.task.done():
                self.task = asyncio.create_task(self._worker())

    def enqueue_missing(self) -> None:
        self.enqueue([a.id for a in self.bundle.project.assets])

    @property
    def busy(self) -> bool:
        return self.current is not None or bool(self.queue)

    async def _worker(self) -> None:
        while True:
            if not self.queue:
                self.wake.clear()
                await self.wake.wait()
                continue
            asset_id = self.queue.pop(0)
            asset = self.bundle.project.asset(asset_id)
            if asset is None:
                continue
            self.current, self.progress[asset_id] = asset_id, 0.0
            try:
                await self._prepare(asset)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # reported in the media list; editing goes on
                self.errors[asset_id] = str(exc)
            finally:
                self.current = None
                self.progress.pop(asset_id, None)

    async def _prepare(self, asset: Asset) -> None:
        source = Path(asset.path)
        if not await asyncio.to_thread(source.is_file):
            raise ValueError("Source media is offline")
        if not (self.still_count(asset) or self.audio_path(asset)):
            await self.quick(asset, source)
        if asset.probe.video is None or self.video_path(asset) is not None:
            return
        await self._encode(asset, source)
        # The video replaces the quick pass.
        shutil.rmtree(self.folder(asset), ignore_errors=True)

    async def _encode(self, asset: Asset, source: Path) -> None:
        probe = await ffmpeg.probe(source)
        v = probe.video
        if v is None:
            return
        caps = get_caps()
        size = proxy_size(*v.display_size, target=VIDEO_HEIGHT)
        fps = proxy_fps(v)
        vf, _ = video_filter(v, size, fps, caps)
        gop = max(1, round(float(fps)))
        target = self.bundle.proxies_dir / f"{_key(asset)}.webm"
        target.parent.mkdir(parents=True, exist_ok=True)
        temp = target.with_name(f".{target.stem}-{uuid.uuid4().hex}.webm")
        args = [
            "-y", "-nostdin", "-i", str(source),
            "-map", "0:v:0", "-map", "0:a:0?", "-sn", "-dn", "-map_metadata", "-1",
            "-vf", vf, "-fps_mode", "cfr",
            "-c:v", "libvpx-vp9", "-deadline", "realtime", "-cpu-used", "8",
            "-row-mt", "1", "-threads", str(encoder_threads()),
            "-crf", "35", "-b:v", "0", "-g", str(gop), "-keyint_min", str(gop),
            "-c:a", "libopus", "-b:a", "96k", "-ac", "2", "-ar", "48000",
            "-f", "webm", str(temp),
        ]  # fmt: skip

        def progress(p: ffmpeg.Progress) -> None:
            if p.fraction is not None:
                self.progress[asset.id] = p.fraction

        try:
            result = await ffmpeg.run(
                args,
                on_progress=progress,
                duration_us=asset.probe.duration_us or None,
                cancel=self.cancel,
                low_priority=True,
                ffmpeg=caps.ffmpeg,
            )
            if result.cancelled:
                raise asyncio.CancelledError
            if not result.ok:
                raise ValueError(f"Preview video failed: {result.stderr_tail}")
            os.replace(temp, target)
        finally:
            temp.unlink(missing_ok=True)

    async def close(self) -> None:
        self.cancel.set()
        self.queue.clear()
        if self.task is not None:
            self.task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self.task
            self.task = None
