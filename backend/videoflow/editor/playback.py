"""Codec-qualified playback proxy for Qt builds without proprietary codecs."""

import asyncio
import hashlib
import os
import uuid
from pathlib import Path

from videoflow.media import ffmpeg
from videoflow.project.models import Asset
from videoflow.project.store import Bundle


class PlaybackProxies:
    def __init__(self, bundle: Bundle) -> None:
        self.bundle = bundle
        self.locks: dict[str, asyncio.Lock] = {}

    async def webm(self, asset: Asset, source: Path) -> Path:
        key = hashlib.sha256((asset.content_hash + ":webm-v1").encode()).hexdigest()[:24]
        target = self.bundle.proxies_dir / f"{key}.webm"
        async with self.locks.setdefault(key, asyncio.Lock()):
            if target.is_file():
                return target
            temp = target.with_name(f".{key}-{uuid.uuid4().hex}.webm")
            args = ["-y", "-i", str(source)]
            if asset.probe.video:
                args += [
                    "-c:v",
                    "libvpx-vp9",
                    "-deadline",
                    "realtime",
                    "-cpu-used",
                    "6",
                    "-crf",
                    "35",
                    "-b:v",
                    "0",
                    "-threads",
                    "2",
                    "-row-mt",
                    "1",
                    "-pix_fmt",
                    "yuv420p",
                ]
            else:
                args += ["-vn"]
            if asset.probe.has_audio:
                args += ["-c:a", "libopus", "-b:a", "128k", "-ar", "48000"]
            else:
                args += ["-an"]
            args += ["-t", f"{asset.probe.duration_us / 1_000_000:.6f}", str(temp)]
            try:
                result = await ffmpeg.run(args)
                if not result.ok:
                    raise ValueError(f"WebM playback proxy failed: {result.stderr_tail}")
                os.replace(temp, target)
                return target
            finally:
                temp.unlink(missing_ok=True)
