"""Sequential cancellable import queue. Assets publish only after preparation succeeds."""

import asyncio
import contextlib
from pathlib import Path
from typing import Any, Literal

from pydantic import Field

from videoflow.core.base import CamelModel
from videoflow.core.ids import new_id
from videoflow.core.time import frames
from videoflow.editor.analysis import AnalysisFile, describe, load_analysis, store_analysis
from videoflow.editor.grouping import (
    MODEL as GROUPING_MODEL,
)
from videoflow.editor.grouping import (
    ClipText,
    best_match,
    clip_sentences,
    encode_vectors,
    read_vectors,
    vectors_path,
)
from videoflow.editor.models import EditorClip, EditorDocument, layout
from videoflow.editor.resolve import editable_document, fit_transform
from videoflow.engines.downloads import missing_models, model_state
from videoflow.jobs.workers import EngineSpec, WorkerPool
from videoflow.media import ffmpeg
from videoflow.media.ingest import ingest_files
from videoflow.media.proxy import build_proxy, build_still_preview
from videoflow.preferences import Preferences, load_preferences
from videoflow.project.commands import AddAsset, SetEditor
from videoflow.project.models import Asset
from videoflow.project.store import Bundle, save_atomic

STILL_SECONDS = 3
"""Length of a new still-image clip."""


class ImportJob(CamelModel):
    id: str
    filename: str
    state: Literal["queued", "running", "waiting-models", "done", "cancelled", "failed"] = "queued"
    progress: float = Field(default=0, ge=0, le=1)
    phase: str = "Waiting"
    error: str | None = None
    asset_id: str | None = None
    cached: bool = False
    analysis_path: str | None = None
    warning: str | None = None
    models_needed: list[str] = Field(default_factory=list)
    inverses: list[dict[str, Any]] = Field(default_factory=list)


class Imports:
    def __init__(
        self,
        bundle: Bundle,
        *,
        preferences: Preferences | None = None,
        require_models: bool = False,
    ) -> None:
        self.bundle = bundle
        self.preferences = preferences or load_preferences()
        self.require_models = require_models
        self.jobs: dict[str, ImportJob] = {}
        self.tasks: dict[str, asyncio.Task[None]] = {}
        self.lock = asyncio.Lock()
        self.workers = WorkerPool(
            {
                "transcriber": EngineSpec(
                    "videoflow.editor.analysis:Transcriber",
                    start_timeout_s=900,
                    kwargs={
                        "asr_engine": self.preferences.asr_engine,
                        "prefer": self.preferences.ai_device,
                    },
                )
            }
        )
        self.proxies: dict[str, Path] = {}

    def submit(self, path: Path, analyse: bool, *, reanalyse: bool = False) -> ImportJob:
        """Import (and analyse) a source; `reanalyse` ignores and replaces its analysis."""
        job = ImportJob(id=new_id("job"), filename=path.name)
        self.jobs[job.id] = job
        self.tasks[job.id] = asyncio.create_task(self._run(job, path, analyse, reanalyse))
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

    async def _run(
        self, job: ImportJob, path: Path, analyse: bool, reanalyse: bool = False
    ) -> None:
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

                if asset.probe.still:
                    preview = await build_still_preview(
                        path, self.bundle.proxies_dir, asset.content_hash
                    )
                    self.proxies[asset.id] = preview
                    asset.model_extra["previewPath"] = str(preview)  # type: ignore[index]
                else:
                    proxy = await build_proxy(
                        path, self.bundle.proxies_dir, asset.content_hash, on_progress=progress
                    )
                    if proxy:
                        self.proxies[asset.id] = proxy.path
                        asset.model_extra["previewPath"] = str(proxy.path)  # type: ignore[index]
                analysis: AnalysisFile | None = None
                qwen_warning = ""
                # A still image has nothing to transcribe.
                if analyse and not asset.probe.still:
                    job.phase, job.progress = "Checking analysis JSON", 0.45
                    analysis = (
                        None if reanalyse else load_analysis(path, asset.content_hash, self.bundle)
                    )
                    job.cached = analysis is not None
                    if analysis is None:
                        if asset.probe.has_audio:
                            while self.require_models and (
                                needed := await asyncio.to_thread(missing_models, self.preferences)
                            ):
                                job.state, job.phase = (
                                    "waiting-models",
                                    "Download missing models in Settings, or cancel import",
                                )
                                job.models_needed = needed
                                await asyncio.sleep(0.35)
                            job.state, job.models_needed = "running", []
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
                                if self.preferences.summary_engine == "qwen" and transcript.words:
                                    job.phase, job.progress = "Summarizing with local Qwen", 0.8
                                    described = await self.workers.call(
                                        "transcriber",
                                        "summarize",
                                        " ".join(w.text for w in transcript.words),
                                    )
                                    if described is None:
                                        qwen_warning = (
                                            "Qwen returned no usable summary; "
                                            "the deterministic summary is used."
                                        )
                                    else:
                                        analysis.summary, analysis.keywords = described
                                        analysis.summary_engine = "qwen2.5-0.5b-instruct"
                                    job.phase, job.progress = "Titling topics with local Qwen", 0.85
                                    analysis.topics = await self.workers.call(
                                        "transcriber", "topics", transcript.words
                                    )
                                    analysis.topics_engine = "qwen2.5-0.5b-instruct"
                                    analysis.summary_scope = (
                                        "First/last 1400 tokens when over 2800 tokens"
                                    )
                            finally:
                                pcm.unlink(missing_ok=True)
                        else:
                            analysis = AnalysisFile(source_hash=asset.content_hash)
                        location, job.warning = store_analysis(
                            path, analysis, self.bundle, overwrite=reanalyse
                        )
                        if qwen_warning:
                            job.warning = " ".join(filter(None, [qwen_warning, job.warning]))
                        job.analysis_path = str(location)
                job.progress, job.phase = 0.9, "Adding to flow"
                if not duplicate:
                    match = None
                    if analysis and analysis.words:
                        job.phase, job.progress = "Matching retakes", 0.9
                        match = await self._match(asset, analysis)
                    job.inverses = self._publish(asset, match)
                elif reanalyse and analysis and analysis.words:
                    # A new analysis may reveal the retake it belongs to: stack it there.
                    job.phase, job.progress = "Matching retakes", 0.9
                    match = await self._match(asset, analysis)
                    if match:
                        job.inverses = self._restack(asset.id, match)
                job.asset_id, job.state, job.progress, job.phase = asset.id, "done", 1, "Ready"
        except asyncio.CancelledError:
            job.state, job.phase = "cancelled", "Cancelled"
            raise
        except Exception as exc:
            job.state, job.phase, job.error = "failed", "Import failed", str(exc)

    async def _clip_text(self, asset: Asset, analysis: AnalysisFile, embed: bool) -> ClipText:
        """Sentences of one source, with cached (or freshly computed) vectors."""
        texts = clip_sentences(analysis.words)
        if not embed or not texts:
            return ClipText(asset.id, texts)
        path = vectors_path(self.bundle.features_dir, asset.content_hash)
        vectors = read_vectors(path, len(texts))
        if vectors is None:
            vectors = await self.workers.call("transcriber", "embed", texts)
            path.parent.mkdir(parents=True, exist_ok=True)
            save_atomic(path, encode_vectors(vectors))
        return ClipText(asset.id, texts, vectors)

    async def _match(self, asset: Asset, analysis: AnalysisFile) -> str | None:
        """Asset id of the clip this source is a retake of (docs/features/retake-grouping.md), if
        any."""
        project = self.bundle.project
        placed = {c.asset_id for c in editable_document(project).clips}
        embed = await asyncio.to_thread(model_state, GROUPING_MODEL) == "up-to-date"
        new = await self._clip_text(asset, analysis, embed)
        candidates = []
        for other in project.assets:
            if other.id == asset.id or other.id not in placed:
                continue
            with contextlib.suppress(ValueError, OSError):
                previous = load_analysis(Path(other.path), other.content_hash, self.bundle)
                if previous and previous.words:
                    candidates.append(await self._clip_text(other, previous, embed))
        found = best_match(new, candidates)
        return found[0] if found else None

    def _restack(self, asset_id: str, match: str) -> list[dict[str, Any]]:
        """Move an asset's clip (with its linked audio) onto a new lane over its retake.

        Only when the asset has a single clip, or one linked pair, in the edit and it is
        not already stacked over the match; otherwise the edit is left as it is.
        """
        project = self.bundle.project
        document = editable_document(project)
        mine = [c for c in document.clips if c.asset_id == asset_id]
        units = {c.link_id or c.id for c in mine}
        matched = next(
            (c for c in document.clips if c.asset_id == match and c.kind == "video"),
            next((c for c in document.clips if c.asset_id == match), None),
        )
        if len(units) != 1 or matched is None:
            return []
        if any(
            c.start < matched.start + matched.duration and matched.start < c.start + c.duration
            for c in mine
        ):
            return []  # already over (or beside) its retake
        layer = max((c.layer for c in document.clips), default=0) + 1
        moved = EditorDocument(
            clips=[
                c.model_copy(update={"start": matched.start, "layer": layer})
                if c.asset_id == asset_id
                else c
                for c in document.clips
            ],
            transitions=document.transitions,
        )
        _, inverses = self.bundle.commit(project.revision, [SetEditor(document=moved)])
        return [command.dump() for command in inverses]

    def _publish(self, asset: Asset, match: str | None) -> list[dict[str, Any]]:
        project = self.bundle.project
        document = editable_document(project)
        _, start = layout(document)
        layer = 0
        matched = next(
            (c for c in document.clips if c.asset_id == match and c.kind == "video"),
            next((c for c in document.clips if c.asset_id == match), None),
        )
        if matched is not None:
            start = matched.start
            layer = max((c.layer for c in document.clips), default=0) + 1
        rate = project.settings.frame_rate
        still = asset.probe.still
        # A still image starts as a 3 s clip (docs/features/still-images.md).
        count = (
            round(STILL_SECONDS * rate.num / rate.den)
            if still
            else frames(asset.probe.duration_us, rate)
        )
        if count < 1:
            raise ValueError("Media is shorter than one project frame")
        link = new_id("lnk") if asset.probe.video and asset.probe.has_audio else None
        video = asset.probe.video
        transform = fit_transform(project.settings, video)
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
                still_frame=0 if still else None,
            )
            for kind in ("video", "audio")
            if (video if kind == "video" else asset.probe.has_audio)
        ]
        updated = EditorDocument(clips=[*document.clips, *added])
        _, inverses = self.bundle.commit(
            project.revision, [AddAsset(asset=asset), SetEditor(document=updated)]
        )
        return [command.dump() for command in inverses]
