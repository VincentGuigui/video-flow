"""Sequential cancellable import queue. Assets publish only after preparation succeeds."""

import asyncio
import contextlib
from pathlib import Path
from typing import Any, Literal

from pydantic import Field

from videoflow.core.base import CamelModel
from videoflow.core.ids import new_id
from videoflow.core.time import frames
from videoflow.editor.analysis import AnalysisFile, describe, load_analysis, similar, store_analysis
from videoflow.editor.models import EditorClip, EditorDocument, Transform, layout
from videoflow.editor.resolve import editable_document
from videoflow.jobs.workers import EngineSpec, WorkerPool
from videoflow.media import ffmpeg
from videoflow.media.ingest import ingest_files
from videoflow.media.proxy import build_proxy
from videoflow.project.commands import AddAsset, SetEditor
from videoflow.project.models import Asset
from videoflow.project.store import Bundle


class ImportJob(CamelModel):
    id: str
    filename: str
    state: Literal["queued", "running", "done", "cancelled", "failed"] = "queued"
    progress: float = Field(default=0, ge=0, le=1)
    phase: str = "Waiting"
    error: str | None = None
    asset_id: str | None = None
    cached: bool = False
    analysis_path: str | None = None
    warning: str | None = None
    inverses: list[dict[str, Any]] = Field(default_factory=list)


class Imports:
    def __init__(self, bundle: Bundle) -> None:
        self.bundle = bundle
        self.jobs: dict[str, ImportJob] = {}
        self.tasks: dict[str, asyncio.Task[None]] = {}
        self.lock = asyncio.Lock()
        self.workers = WorkerPool(
            {
                "transcriber": EngineSpec(
                    "videoflow.editor.analysis:Transcriber", start_timeout_s=900
                )
            }
        )
        self.proxies: dict[str, Path] = {}

    def submit(self, path: Path, analyse: bool) -> ImportJob:
        job = ImportJob(id=new_id("job"), filename=path.name)
        self.jobs[job.id] = job
        self.tasks[job.id] = asyncio.create_task(self._run(job, path, analyse))
        return job

    async def cancel(self, job_id: str | None = None) -> None:
        keys = [job_id] if job_id else list(self.tasks)
        for key in keys:
            task = self.tasks.get(key)
            job = self.jobs.get(key)
            if task is not None and not task.done():
                task.cancel()
                if job:
                    job.state, job.phase = "cancelled", "Cancelled"
        await asyncio.gather(
            *(self.tasks[k] for k in keys if k in self.tasks), return_exceptions=True
        )

    async def close(self) -> None:
        await self.cancel()
        await self.workers.aclose()

    async def _run(self, job: ImportJob, path: Path, analyse: bool) -> None:
        try:
            async with self.lock:
                job.state, job.phase = "running", "Reading media"
                result = await ingest_files(
                    [path], known=self.bundle.project.assets, base_dir=self.bundle.path.parent
                )
                if result.failures:
                    raise ValueError(result.failures[0].error)
                duplicate = bool(result.duplicates)
                if duplicate:
                    known_id = result.duplicates[0].of_asset_id
                    existing = self.bundle.project.asset(known_id or "")
                    if existing is None:
                        raise ValueError("Duplicate source could not be matched to an asset")
                    job.asset_id = existing.id
                    if not analyse:
                        job.state, job.progress, job.phase = "done", 1, "Already imported"
                        return
                    asset = existing.model_copy(deep=True)
                else:
                    asset = result.assets[0]
                job.progress, job.phase = 0.1, "Preparing playback"

                def progress(p: ffmpeg.Progress) -> None:
                    job.progress = 0.1 + 0.3 * (p.fraction or 0)

                proxy = await build_proxy(
                    path, self.bundle.proxies_dir, asset.content_hash, on_progress=progress
                )
                if proxy:
                    self.proxies[asset.id] = proxy.path
                    asset.model_extra["previewPath"] = str(proxy.path)  # type: ignore[index]
                analysis: AnalysisFile | None = None
                if analyse:
                    job.phase, job.progress = "Checking analysis JSON", 0.45
                    analysis = load_analysis(path, asset.content_hash, self.bundle)
                    job.cached = analysis is not None
                    if analysis is None:
                        if asset.probe.has_audio:
                            job.phase = (
                                "Loading speech models / transcribing; "
                                "first run may download models"
                            )
                            pcm = self.bundle.cache_dir / f"{job.id}.f32"
                            try:
                                result_ff = await ffmpeg.run(
                                    [
                                        "-y",
                                        "-i",
                                        str(path),
                                        "-vn",
                                        "-ac",
                                        "1",
                                        "-ar",
                                        "16000",
                                        "-f",
                                        "f32le",
                                        str(pcm),
                                    ]
                                )
                                if not result_ff.ok:
                                    raise ValueError(result_ff.stderr_tail)
                                transcript = await self.workers.call(
                                    "transcriber",
                                    "transcribe",
                                    pcm.read_bytes(),
                                    self.bundle.project.settings.language,
                                )
                                analysis = describe(transcript, asset.content_hash)
                            finally:
                                pcm.unlink(missing_ok=True)
                        else:
                            analysis = AnalysisFile(source_hash=asset.content_hash)
                        location, job.warning = store_analysis(path, analysis, self.bundle)
                        job.analysis_path = str(location)
                job.progress, job.phase = 0.9, "Adding to flow"
                if not duplicate:
                    job.inverses = self._publish(asset, analysis)
                job.asset_id, job.state, job.progress, job.phase = asset.id, "done", 1, "Ready"
        except asyncio.CancelledError:
            job.state, job.phase = "cancelled", "Cancelled"
            raise
        except Exception as exc:
            job.state, job.phase, job.error = "failed", "Import failed", str(exc)

    def _publish(self, asset: Asset, analysis: AnalysisFile | None) -> list[dict[str, Any]]:
        project = self.bundle.project
        document = editable_document(project)
        _, start = layout(document)
        layer = 0
        if analysis:
            for other in project.assets:
                with contextlib.suppress(ValueError, OSError):
                    previous = load_analysis(Path(other.path), other.content_hash, self.bundle)
                    matched = next((c for c in document.clips if c.asset_id == other.id), None)
                    if previous and matched and similar(analysis, previous):
                        start = matched.start
                        layer = max((c.layer for c in document.clips), default=0) + 1
                        break
        count = frames(asset.probe.duration_us, project.settings.frame_rate)
        if count < 1:
            raise ValueError("Media is shorter than one project frame")
        link = new_id("lnk") if asset.probe.video and asset.probe.has_audio else None
        video = asset.probe.video
        transform = Transform(width=project.settings.width, height=project.settings.height)
        if video:
            factor = min(
                project.settings.width / video.width, project.settings.height / video.height
            )
            transform = Transform(
                width=video.width * factor,
                height=video.height * factor,
                x=(project.settings.width - video.width * factor) / 2,
                y=(project.settings.height - video.height * factor) / 2,
            )
        added = [
            EditorClip(
                id=new_id("clp"),
                kind=kind,
                asset_id=asset.id,
                name=Path(asset.path).name,
                start=start,
                source_in=0,
                source_out=count,
                layer=layer,
                link_id=link,
                transform=transform,
            )
            for kind in ("video", "audio")
            if (video if kind == "video" else asset.probe.has_audio)
        ]
        updated = EditorDocument(clips=[*document.clips, *added])
        _, inverses = self.bundle.commit(
            project.revision, [AddAsset(asset=asset), SetEditor(document=updated)]
        )
        return [command.dump() for command in inverses]
