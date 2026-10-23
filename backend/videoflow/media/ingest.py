"""Ingest: scan a folder, probe, hash, skip duplicates (ING-04), build Assets, prepare caches."""

from __future__ import annotations

import asyncio
import os
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import UTC
from pathlib import Path

from videoflow.core import ids
from videoflow.core.time import Rational
from videoflow.media import ffmpeg
from videoflow.media.caps import FFmpegCaps, get_caps
from videoflow.media.hashing import content_hash
from videoflow.media.peaks import PeaksResult, compute_peaks
from videoflow.media.proxy import ProxyResult, build_proxy
from videoflow.media.thumbs import ThumbsResult, build_thumbs
from videoflow.project.models import Asset, AssetProbe, AudioStreamInfo, VideoStreamInfo
from videoflow.project.store import Bundle

MEDIA_EXTENSIONS = frozenset({
    ".mp4", ".mov", ".m4v", ".mkv", ".webm", ".avi", ".mts", ".m2ts", ".mxf", ".mpg", ".mpeg",
    ".wmv", ".3gp",
    ".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg", ".opus", ".aif", ".aiff",
})  # fmt: skip
PROBE_CONCURRENCY = 4
MIN_RELIABLE_YEAR = 2000


@dataclass(frozen=True)
class Duplicate:
    path: Path
    of_asset_id: str | None
    """Asset already in the project, or None when the twin is in the same batch."""
    of_path: Path


@dataclass(frozen=True)
class Failure:
    path: Path
    error: str


@dataclass
class IngestResult:
    assets: list[Asset] = field(default_factory=list)
    duplicates: list[Duplicate] = field(default_factory=list)
    failures: list[Failure] = field(default_factory=list)


def scan_media(folder: Path | str) -> list[Path]:
    """Media files under `folder` (recursive, hidden entries skipped), sorted by path."""
    found: list[Path] = []
    for root, dirs, files in os.walk(folder):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        found += [
            Path(root) / f
            for f in files
            if not f.startswith(".") and Path(f).suffix.lower() in MEDIA_EXTENSIONS
        ]
    return sorted(found)


def _hdr(transfer: str | None) -> str:
    return {"arib-std-b67": "hlg", "smpte2084": "pq"}.get(transfer or "", "none")


def asset_probe(pr: ffmpeg.ProbeResult) -> AssetProbe:
    video = None
    if pr.video is not None:
        v = pr.video
        fps = v.fps if v.fps > 0 else v.r_fps
        video = VideoStreamInfo(
            width=v.width,
            height=v.height,
            rotation=v.rotation,
            frame_rate=Rational(num=fps.numerator, den=fps.denominator)
            if fps > 0
            else Rational(num=30),
            vfr=v.is_vfr,
            hdr=_hdr(v.color_transfer),
            codec=v.codec,
        )
    audio = [
        AudioStreamInfo(
            index=i,
            channels=max(a.channels, 1),
            sample_rate=max(a.sample_rate, 1),
            codec=a.codec,
            language=a.language,
        )
        for i, a in enumerate(pr.audio)
    ]
    durations = [d for d in (pr.duration_us, pr.video.duration_us if pr.video else None) if d]
    created = pr.creation_time
    return AssetProbe(
        duration_us=max(durations, default=0),
        video=video,
        audio_streams=audio,
        creation_time=created.astimezone(UTC).isoformat() if created else None,
        creation_time_reliable=created is not None and created.year >= MIN_RELIABLE_YEAR,
    )


async def ingest_files(
    paths: Iterable[Path | str],
    *,
    known: Iterable[Asset] = (),
    base_dir: Path | str | None = None,
    on_progress: Callable[[int, int], object] | None = None,
    cancel: asyncio.Event | None = None,
    ffprobe: Path | str | None = None,
) -> IngestResult:
    """Probe and hash `paths`; files whose content hash is in `known` or repeats are skipped.

    `base_dir` (the bundle's parent folder) fills `Asset.rel_path` for relinking.
    """
    files = _resolve_all(paths)
    by_hash: dict[str, tuple[str | None, Path]] = {
        a.content_hash: (a.id, Path(a.path)) for a in known
    }
    result = IngestResult()
    sem = asyncio.Semaphore(PROBE_CONCURRENCY)

    async def work(p: Path) -> tuple[str, ffmpeg.ProbeResult] | Failure:
        async with sem:
            try:
                pr = await ffmpeg.probe(p, ffprobe)
                if pr.video is None and not pr.audio:
                    return Failure(p, "no audio or video stream")
                return await content_hash(p), pr
            except (ffmpeg.ProbeError, OSError) as exc:
                return Failure(p, str(exc))

    tasks = [asyncio.create_task(work(p)) for p in files]
    try:
        for i, (p, task) in enumerate(zip(files, tasks, strict=True), start=1):
            if cancel is not None and cancel.is_set():
                break
            out = await task
            if isinstance(out, Failure):
                result.failures.append(out)
            else:
                digest, pr = out
                if digest in by_hash:
                    other_id, other_path = by_hash[digest]
                    result.duplicates.append(Duplicate(p, other_id, other_path))
                else:
                    asset = Asset(
                        id=ids.new_id(ids.ASSET),
                        path=str(p),
                        rel_path=_rel(p, base_dir),
                        content_hash=digest,
                        probe=asset_probe(pr),
                    )
                    by_hash[digest] = (None, p)
                    result.assets.append(asset)
            if on_progress is not None:
                on_progress(i, len(files))
    finally:
        for t in tasks:
            t.cancel()
    return result


def _resolve_all(paths: Iterable[Path | str]) -> list[Path]:
    return [Path(p).resolve() for p in paths]


def _rel(p: Path, base: Path | str | None) -> str | None:
    if base is None:
        return None
    try:
        return Path(os.path.relpath(p, Path(base).resolve())).as_posix()
    except ValueError:  # different drive on Windows
        return None


async def ingest_folder(folder: Path | str, **kwargs: object) -> IngestResult:
    """`ingest_files` over every media file below `folder`."""
    return await ingest_files(scan_media(folder), **kwargs)  # type: ignore[arg-type]


@dataclass(frozen=True)
class PreparedAsset:
    asset_id: str
    proxy: ProxyResult | None
    thumbs: ThumbsResult | None
    peaks: PeaksResult | None

    @property
    def fully_cached(self) -> bool:
        return all(r is None or r.cached for r in (self.proxy, self.thumbs, self.peaks))


def peaks_path(bundle: Bundle, asset: Asset) -> Path:
    return bundle.features_dir / f"{asset.content_hash[:16]}.peaks.bin"


async def prepare_asset(
    bundle: Bundle,
    asset: Asset,
    *,
    hw: str = "auto",
    caps: FFmpegCaps | None = None,
    on_stage: Callable[[str], object] | None = None,
    cancel: asyncio.Event | None = None,
) -> PreparedAsset:
    """Proxy, thumbnails and peaks of `asset` into the bundle caches (S1). Idempotent."""
    caps = caps or get_caps()
    pr = await ffmpeg.probe(asset.path, caps.ffprobe)

    def stage(name: str) -> None:
        if on_stage is not None:
            on_stage(name)

    proxy = thumbs = peaks = None
    if pr.video is not None:
        stage("proxy")
        proxy = await build_proxy(
            asset.path, bundle.proxies_dir, asset.content_hash,
            probe=pr, hw=hw, caps=caps, cancel=cancel,
        )  # fmt: skip
        assert proxy is not None
        stage("thumbs")
        thumbs = await build_thumbs(
            proxy.path, bundle.thumbs_dir, asset.content_hash,
            display_size=pr.video.display_size,
            duration_us=asset.probe.duration_us or pr.duration_us or 0,
            caps=caps, cancel=cancel,
        )  # fmt: skip
    if pr.audio:
        stage("peaks")
        peaks = await compute_peaks(
            asset.path, peaks_path(bundle, asset), cancel=cancel, ffmpeg=caps.ffmpeg
        )
    return PreparedAsset(asset.id, proxy, thumbs, peaks)
