"""Command line entry point (``videoflow``)."""

import json
import sys
from pathlib import Path
from typing import Annotated

import typer

from videoflow import __version__

app = typer.Typer(invoke_without_command=True, help="Video-Flow desktop editor and headless tools.")


@app.callback()
def main(ctx: typer.Context) -> None:
    """Video-Flow command line."""
    if ctx.invoked_subcommand is None:
        desktop()


@app.command()
def version() -> None:
    """Print the Video-Flow version."""
    typer.echo(__version__)


@app.command()
def desktop(
    project: Annotated[Path | None, typer.Option(help="Project bundle to open or create.")] = None,
) -> None:
    """Open the native PySide6/Qt WebEngine application."""
    import multiprocessing
    import os

    from videoflow.desktop import startup  # first: the startup timeline starts here
    from videoflow.project.models import new_project
    from videoflow.project.store import Bundle

    multiprocessing.freeze_support()
    try:
        from videoflow.desktop.host import run_desktop
    except ImportError as exc:
        typer.echo("Desktop runtime missing. Install with: uv sync --extra desktop", err=True)
        raise typer.Exit(1) from exc
    startup.mark("qt")
    if getattr(sys, "frozen", False):
        import threading

        from videoflow.updates import cleanup

        # Files of an applied update: deleted in the background (large _internal folders).
        threading.Thread(target=cleanup, name="update-cleanup", daemon=True).start()
    if project is None:
        from videoflow.project.library import LEGACY_SUFFIX, ProjectLibrary, is_project
        from videoflow.runtime import recent_projects_file, user_data_dir

        library = ProjectLibrary(recent_projects_file())
        if not library.entries():
            # Projects of earlier versions lived in a per-user library: list them once.
            legacy = Path(os.environ.get("LOCALAPPDATA", Path.home() / ".local" / "share"))
            for old in sorted((legacy / "Video-Flow").glob(f"*{LEGACY_SUFFIX}")):
                if is_project(old):
                    library.add(Bundle(old))
        latest = library.latest()
        if latest is not None:
            raise typer.Exit(run_desktop(latest))
        # No project yet: start on the home page; an internal placeholder backs the API.
        placeholder = user_data_dir() / "placeholder.video-flow"
        bundle = (
            Bundle(placeholder)
            if (placeholder / "project.json").exists()
            else Bundle.create(placeholder, new_project("Untitled"))
        )
        raise typer.Exit(run_desktop(bundle, project_open=False))
    path = project.resolve()
    bundle = (
        Bundle(path)
        if (path / "project.json").exists()
        else Bundle.create(path, new_project(path.stem))
    )
    raise typer.Exit(run_desktop(bundle))


@app.command("desktop-check", hidden=True)
def desktop_check(media: Path, output: Path, features: bool = False) -> None:
    """Run native Qt checks in a development or packaged runtime."""
    from videoflow.desktop.smoke import main as smoke

    raise typer.Exit(
        smoke(
            ["--media", str(media), "--output", str(output), *(["--features"] if features else [])]
        )
    )


@app.command()
def serve(
    project: Annotated[Path, typer.Option(help="Project bundle to open or create.")] = Path(
        "edit.video-flow"
    ),
    port: Annotated[int, typer.Option(min=1024, max=65535)] = 8765,
    media_root: Annotated[
        list[Path] | None, typer.Option(help="Allowed local import root; repeatable.")
    ] = None,
    open_browser: Annotated[bool, typer.Option(help="Open the editor in the browser.")] = True,
) -> None:
    """Start explicit browser/diagnostic mode (normal launch uses the desktop window)."""
    import secrets
    import threading
    import webbrowser

    import uvicorn

    from videoflow.api.app import create_app
    from videoflow.project.models import new_project
    from videoflow.project.store import Bundle

    path = project.resolve()
    bundle = (
        Bundle(path)
        if (path / "project.json").exists()
        else Bundle.create(path, new_project(path.stem))
    )
    token = secrets.token_urlsafe(32)
    url = f"http://127.0.0.1:{port}/?token={token}"
    typer.echo(f"Video-Flow: {url}")
    application = create_app(bundle, token=token, port=port, media_roots=media_root)
    if open_browser:
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    uvicorn.run(application, host="127.0.0.1", port=port, log_level="info")


@app.command("export")
def export_command(
    project_path: Annotated[Path, typer.Argument(help="Project bundle or project.json file.")],
    output: Annotated[
        Path | None, typer.Option(help="Output directory (default: bundle/exports).")
    ] = None,
    otio: Annotated[bool, typer.Option("--otio", help="Export an OTIO timeline.")] = False,
    otioz: Annotated[bool, typer.Option("--otioz", help="Bundle OTIO and source media.")] = False,
    edl: Annotated[
        bool, typer.Option("--edl", help="Export CMX 3600 V1 with reel mapping.")
    ] = False,
    srt: Annotated[
        bool, typer.Option("--srt", help="Export subtitles from supplied transcripts.")
    ] = False,
    paper_edit: Annotated[
        bool, typer.Option("--paper-edit", help="Export Markdown and CSV.")
    ] = False,
    camtasia: Annotated[
        bool, typer.Option("--camtasia", help="Export a Camtasia project (.tscproj).")
    ] = False,
    camtasia_template: Annotated[
        Path | None,
        typer.Option(help="Camtasia project to clone structures from (default: app templates/)."),
    ] = None,
    transcripts: Annotated[
        Path | None,
        typer.Option(
            help="JSON mapping asset IDs to Transcript objects; word times are source microseconds."
        ),
    ] = None,
    include_alternates: Annotated[
        bool, typer.Option(help="Add disabled ALT tracks to OTIO.")
    ] = False,
    overwrite: Annotated[bool, typer.Option(help="Replace existing exports.")] = False,
) -> None:
    """Export an authored edit. Defaults to OTIO when no format flags are supplied."""
    from pydantic import TypeAdapter, ValidationError

    from videoflow.analysis.types import Transcript
    from videoflow.exporters.service import export_project
    from videoflow.project.store import Bundle, ProjectStoreError

    try:
        bundle = Bundle(project_path.parent if project_path.is_file() else project_path)
        if project_path.is_file() and project_path.name != "project.json":
            raise ValueError("Expected a project bundle or a file named project.json")
        project = bundle.load()
        words = None
        if transcripts is not None:
            words = TypeAdapter(dict[str, Transcript]).validate_json(transcripts.read_bytes())
        formats = [
            name
            for name, selected in (
                ("otio", otio),
                ("otioz", otioz),
                ("edl", edl),
                ("srt", srt),
                ("paper-edit", paper_edit),
                ("camtasia", camtasia),
            )
            if selected
        ] or ["otio"]
        paths = export_project(
            project,
            output or bundle.exports_dir,
            formats,
            transcripts=words,
            include_alternates=include_alternates,
            overwrite=overwrite,
            camtasia_template=camtasia_template,
        )
    except (OSError, ValueError, ProjectStoreError, ValidationError) as exc:
        typer.echo(f"Export failed: {exc}", err=True)
        raise typer.Exit(1) from exc
    for path in paths:
        typer.echo(str(path.resolve()))
    report = json.loads(paths[-1].read_text(encoding="utf-8"))
    for warning in report["warnings"]:
        typer.echo(f"Warning: {warning}", err=True)


@app.command("apply-update", hidden=True)
def apply_update(
    target: Annotated[Path, typer.Option(help="Application folder to update.")],
    pid: Annotated[int, typer.Option(help="Process to wait for (the running old version).")],
) -> None:
    """Replace the application in `target` with this one, then start it (contract between
    versions: docs/features/getting-started/updates.md)."""
    import logging

    from videoflow.runtime import application_dir, user_data_dir
    from videoflow.updates import apply

    logs = user_data_dir() / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=logs / "update.log", level=logging.INFO)
    logging.info("Applying %s to %s after process %s", __version__, target, pid)
    try:
        apply(application_dir(), target.resolve(), pid)
    except Exception as exc:
        raise typer.Exit(1) from exc
    logging.info("Update applied")


@app.command("components-check", hidden=True)
def components_check(output: Path) -> None:
    """Validate the packaged inference runtime without models or a desktop window."""
    from videoflow.hw.ai import available_providers, cuda_status

    cuda = cuda_status()
    output.write_text(
        json.dumps(
            {"version": __version__, "providers": available_providers(), "cuda": cuda}, indent=2
        ),
        encoding="utf-8",
    )
    if cuda is not None and not cuda["available"]:
        raise typer.Exit(1)
