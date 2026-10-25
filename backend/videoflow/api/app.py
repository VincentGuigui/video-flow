"""Authenticated loopback editor API and built SPA; one selected project per process."""

import asyncio
import hashlib
import json
import secrets
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, StreamingResponse
from pydantic import Field

from videoflow.core.base import CamelModel
from videoflow.desktop.grants import SelectionGrants
from videoflow.editor.analysis import AnalysisFile, load_analysis
from videoflow.editor.imports import Imports
from videoflow.editor.playback import PlaybackProxies
from videoflow.editor.resolve import editable_document
from videoflow.exporters.service import export_project
from videoflow.media import ffmpeg
from videoflow.media.hashing import content_hash
from videoflow.media.ingest import MEDIA_EXTENSIONS
from videoflow.media.peaks import compute_peaks, read_peaks
from videoflow.media.proxy import build_proxy
from videoflow.project.commands import Command, RelinkAsset
from videoflow.project.store import Bundle, ProjectStoreError, StaleRevisionError


class Patch(CamelModel):
    base_revision: int = Field(ge=0)
    commands: list[Command] = Field(max_length=100)


class PathImport(CamelModel):
    path: str
    analyse: bool = True


class OutputRequest(CamelModel):
    formats: list[str] = Field(default_factory=lambda: ["otio"])


class NativeSelection(CamelModel):
    paths: list[str] = Field(max_length=500)
    asset_id: str | None = None


class NativeImport(CamelModel):
    handle: str
    analyse: bool = True
    asset_id: str | None = None


def create_app(
    bundle: Bundle,
    *,
    token: str,
    port: int = 8765,
    media_roots: list[Path] | None = None,
    frontend: Path | None = None,
    desktop_secret: str | None = None,
    allow_uploads: bool = False,
) -> FastAPI:
    imports = Imports(bundle)
    playbacks = PlaybackProxies(bundle)
    roots = [p.resolve() for p in (media_roots or [bundle.path.parent])]
    host = f"127.0.0.1:{port}"
    resources = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[3]))
    static = frontend or resources / "frontend" / "dist"
    mutation_lock = asyncio.Lock()
    uploads: set[tuple[str, str]] = set()
    grants = SelectionGrants()
    trusted_assets = {a.id: a.dump() for a in bundle.project.assets}
    trusted_paths = {a.id: {a.path} for a in bundle.project.assets}

    def check_commands(commands: list[Command]) -> None:
        # The renderer cannot manufacture source paths through general project commands.
        for command in commands:
            if command.type == "Batch":
                check_commands(command.commands)
            elif command.type == "AddAsset":
                expected = trusted_assets.get(command.asset.id)
                if expected is None or expected != command.asset.dump():
                    raise HTTPException(403, "Import sources through a native selection")
            elif command.type == "RelinkAsset":
                if command.path not in trusted_paths.get(command.asset_id, set()):
                    raise HTTPException(403, "Relink through a native file selection")
            elif command.type not in ("SetEditor", "SetSettings", "RenameProject", "RemoveAsset"):
                raise HTTPException(403, "Command is not exposed by the interactive editor")

    @asynccontextmanager
    async def lifespan(_: FastAPI):  # type: ignore[no-untyped-def]
        yield
        await imports.close()

    app = FastAPI(title="Video-Flow local editor", lifespan=lifespan)
    app.state.imports = imports

    @app.middleware("http")
    async def authentication(request: Request, call_next: Any) -> Any:
        if request.headers.get("host") != host:
            return JSONResponse({"detail": "Invalid Host"}, status_code=403)
        origin = request.headers.get("origin")
        if origin and urlsplit(origin).netloc != host:
            return JSONResponse({"detail": "Invalid Origin"}, status_code=403)
        supplied = request.query_params.get("token")
        if request.url.path == "/" and supplied is not None:
            if not secrets.compare_digest(supplied, token):
                return JSONResponse({"detail": "Invalid launch token"}, status_code=401)
            response = RedirectResponse("/", status_code=303)
            response.set_cookie("videoflow", token, httponly=True, samesite="strict")
            response.headers["Referrer-Policy"] = "no-referrer"
            return response
        if not secrets.compare_digest(request.cookies.get("videoflow", ""), token):
            return JSONResponse(
                {"detail": "Open the launch URL printed in your terminal"}, status_code=401
            )
        response = await call_next(request)
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.get("/api/project")
    async def project() -> dict[str, Any]:
        p = bundle.project
        trusted_assets.update({a.id: a.dump() for a in p.assets})
        return {
            "project": p.dump(),
            "editor": editable_document(p).dump(),
            "mediaRoots": [str(p) for p in roots],
            "desktop": desktop_secret is not None,
            "offline": await asyncio.to_thread(
                lambda: [a.id for a in p.assets if not Path(a.path).is_file()]
            ),
        }

    @app.patch("/api/project")
    async def patch(payload: Patch) -> dict[str, Any]:
        async with mutation_lock:
            trusted_assets.update({a.id: a.dump() for a in bundle.project.assets})
            check_commands(payload.commands)
            try:
                p, inverses = bundle.commit(payload.base_revision, payload.commands)
            except StaleRevisionError as exc:
                raise HTTPException(409, str(exc)) from exc
            except (ValueError, ProjectStoreError) as exc:
                raise HTTPException(422, str(exc)) from exc
        return {
            "project": p.dump(),
            "editor": editable_document(p).dump(),
            "inverses": [c.dump() for c in inverses],
        }

    @app.get("/api/jobs")
    async def jobs() -> list[dict[str, Any]]:
        return [j.dump() for j in imports.jobs.values()]

    @app.post("/api/jobs/cancel")
    async def cancel(job_id: str | None = None) -> dict[str, bool]:
        await imports.cancel(job_id)
        return {"ok": True}

    @app.post("/api/import-path")
    async def import_path(payload: PathImport) -> dict[str, Any]:
        path = await asyncio.to_thread(Path(payload.path).resolve)
        if not any(path.is_relative_to(root) for root in roots):
            raise HTTPException(403, "Path is outside the configured media roots")
        if not path.is_file() or path.suffix.casefold() not in MEDIA_EXTENSIONS:
            raise HTTPException(422, "Select a supported video or audio file")
        return imports.submit(path, payload.analyse).dump()

    @app.post("/api/desktop/selection")
    async def native_selection(payload: NativeSelection, request: Request) -> Any:
        supplied = request.headers.get("x-videoflow-desktop", "")
        if desktop_secret is None or not secrets.compare_digest(supplied, desktop_secret):
            raise HTTPException(403, "Native host authentication required")
        if payload.asset_id is not None and bundle.project.asset(payload.asset_id) is None:
            raise HTTPException(404, "Unknown relink asset")
        try:
            return {
                "selections": grants.issue([Path(p) for p in payload.paths], payload.asset_id),
                "assetId": payload.asset_id,
            }
        except (OSError, ValueError) as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.post("/api/native-import")
    async def native_import(payload: NativeImport) -> Any:
        try:
            path = grants.consume(payload.handle)
        except ValueError as exc:
            raise HTTPException(403, str(exc)) from exc
        return imports.submit(path, payload.analyse).dump()

    @app.post("/api/native-relink")
    async def native_relink(payload: NativeImport) -> Any:
        if payload.asset_id is None:
            raise HTTPException(422, "Select an asset to relink")
        try:
            path = grants.consume(payload.handle, asset_id=payload.asset_id)
        except ValueError as exc:
            raise HTTPException(403, str(exc)) from exc
        asset = bundle.project.asset(payload.asset_id)
        if asset is None:
            raise HTTPException(404)
        if await content_hash(path) != asset.content_hash:
            raise HTTPException(422, "Selected file does not match the original media fingerprint")
        relative = (
            path.relative_to(bundle.path.parent).as_posix()
            if path.is_relative_to(bundle.path.parent)
            else None
        )
        p, inverses = bundle.commit(
            bundle.project.revision,
            [
                RelinkAsset(
                    asset_id=asset.id,
                    path=str(path),
                    rel_path=relative,
                )
            ],
        )
        trusted_assets.update({a.id: a.dump() for a in p.assets})
        trusted_paths.setdefault(asset.id, {asset.path}).add(str(path))
        return {"project": p.dump(), "inverses": [c.dump() for c in inverses]}

    @app.post("/api/uploads/{batch_id}/{filename}")
    async def upload(batch_id: str, filename: str, request: Request, analyse: bool = True) -> Any:
        if not allow_uploads or desktop_secret is not None:
            raise HTTPException(
                403, "Byte uploads are disabled; select original files in the desktop app"
            )
        if (
            not batch_id.isalnum()
            or len(batch_id) > 64
            or filename != Path(filename).name
            or "/" in filename
            or "\\" in filename
            or ":" in filename
            or filename in (".", "..")
        ):
            raise HTTPException(422, "Invalid upload name")
        suffix = Path(filename).suffix.casefold()
        if suffix not in MEDIA_EXTENSIONS and suffix != ".json":
            raise HTTPException(422, "Unsupported media type")
        folder = bundle.path / "media" / batch_id
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / filename
        key = (batch_id, filename)
        if key in uploads or target.exists():
            raise HTTPException(409, "File already uploaded")
        uploads.add(key)
        temporary = target.with_name(target.name + ".upload")
        try:
            with temporary.open("xb") as handle:
                async for chunk in request.stream():
                    handle.write(chunk)
            if suffix == ".json":
                if temporary.stat().st_size > 20 * 1024 * 1024:
                    raise HTTPException(422, "Analysis JSON is too large")
                AnalysisFile.model_validate_json(temporary.read_bytes())
            temporary.replace(target)
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
        finally:
            uploads.discard(key)
        return (
            {"sidecar": filename} if suffix == ".json" else imports.submit(target, analyse).dump()
        )

    @app.get("/api/media/{asset_id}")
    async def media(asset_id: str, codec: Literal["auto", "webm"] = "auto") -> FileResponse:
        asset = bundle.project.asset(asset_id)
        if asset is None:
            raise HTTPException(404, "Unknown asset")
        path = Path(asset.path)
        if asset.probe.video:
            preview = (asset.model_extra or {}).get("previewPath")
            proxy_path = Path(preview) if preview else imports.proxies.get(asset_id)
            if proxy_path is not None and not proxy_path.resolve().is_relative_to(
                bundle.proxies_dir.resolve()
            ):
                proxy_path = None
            if proxy_path is None or not proxy_path.is_file():
                result = await build_proxy(path, bundle.proxies_dir, asset.content_hash)
                proxy_path = result.path if result else path
                imports.proxies[asset_id] = proxy_path
            path = proxy_path
        if not path.is_file():
            raise HTTPException(404, "Source media is missing")
        if codec == "webm":
            try:
                path = await playbacks.webm(asset, path)
            except (ValueError, OSError) as exc:
                raise HTTPException(422, str(exc)) from exc
        return FileResponse(path)  # Starlette handles byte-range requests (206/416).

    @app.get("/api/analysis/{asset_id}")
    async def analysis(asset_id: str) -> Any:
        asset = bundle.project.asset(asset_id)
        if asset is None:
            raise HTTPException(404, "Unknown asset")
        try:
            result = load_analysis(Path(asset.path), asset.content_hash, bundle)
        except (ValueError, OSError) as exc:
            raise HTTPException(422, str(exc)) from exc
        return result.dump() if result else None

    @app.get("/api/waveform/{asset_id}")
    async def waveform(asset_id: str) -> Any:
        asset = bundle.project.asset(asset_id)
        if asset is None:
            raise HTTPException(404)
        if not asset.probe.has_audio:
            return {"pps": 1, "rms": []}
        key = hashlib.sha256(asset.content_hash.encode()).hexdigest()[:24]
        target = bundle.cache_dir / "peaks" / (key + ".bin")
        await compute_peaks(Path(asset.path), target)
        peaks = read_peaks(target)
        step = max(1, peaks.count // 2000)
        return {"pps": peaks.peaks_per_second / step, "rms": peaks.rms[::step].tolist()}

    @app.get("/api/thumbnail/{asset_id}")
    async def thumbnail(asset_id: str) -> FileResponse:
        asset = bundle.project.asset(asset_id)
        if asset is None or asset.probe.video is None:
            raise HTTPException(404)
        key = hashlib.sha256(asset.content_hash.encode()).hexdigest()[:24]
        target = bundle.thumbs_dir / f"{key}.jpg"
        if not target.is_file():
            proxy = await build_proxy(Path(asset.path), bundle.proxies_dir, asset.content_hash)
            source = proxy.path if proxy else Path(asset.path)
            result = await ffmpeg.run(
                ["-y", "-i", str(source), "-frames:v", "1", "-vf", "scale=240:-2", str(target)]
            )
            if not result.ok:
                raise HTTPException(422, "Could not create thumbnail")
        return FileResponse(target)

    @app.post("/api/export")
    async def export(payload: OutputRequest) -> Any:
        try:
            from videoflow.analysis.types import Transcript

            transcripts = {}
            for asset in bundle.project.assets:
                result = load_analysis(Path(asset.path), asset.content_hash, bundle)
                if result:
                    transcripts[asset.id] = Transcript(words=result.words)
            paths = export_project(
                bundle.project,
                bundle.exports_dir,
                payload.formats,
                transcripts=transcripts,
                overwrite=True,
            )
            return {"files": [str(p) for p in paths]}
        except (ValueError, OSError) as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.get("/api/events")
    async def events(request: Request) -> StreamingResponse:
        async def stream() -> AsyncIterator[str]:
            previous = ""
            while not await request.is_disconnected():
                data = json.dumps(
                    {
                        "revision": bundle.project.revision,
                        "jobs": [j.dump() for j in imports.jobs.values()],
                    }
                )
                if data != previous:
                    yield f"data: {data}\n\n"
                    previous = data
                else:
                    yield ": keepalive\n\n"
                await asyncio.sleep(0.5)

        return StreamingResponse(stream(), media_type="text/event-stream")

    @app.get("/{path:path}")
    async def frontend_file(path: str) -> Any:
        candidate = (static / path).resolve()
        if path.startswith("api/"):
            raise HTTPException(404)
        if not candidate.is_relative_to(static.resolve()):
            raise HTTPException(403)
        if candidate.is_file():
            return FileResponse(candidate)
        index = static / "index.html"
        if index.is_file():
            return FileResponse(index)
        return JSONResponse(
            {"detail": "Build the frontend: cd frontend && npm install && npm run build"},
            status_code=503,
        )

    return app
