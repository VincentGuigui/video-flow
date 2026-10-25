"""Command line entry point (``videoflow``)."""

import json
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

    from videoflow.project.models import new_project
    from videoflow.project.store import Bundle

    multiprocessing.freeze_support()
    try:
        from videoflow.desktop.host import run_desktop
    except ImportError as exc:
        typer.echo("Desktop runtime missing. Install with: uv sync --extra desktop", err=True)
        raise typer.Exit(1) from exc
    if project is None:
        root = Path(os.environ.get("LOCALAPPDATA", Path.home() / ".local" / "share"))
        project = root / "Video-Flow" / "Untitled.videoflow"
    path = project.resolve()
    bundle = (
        Bundle(path)
        if (path / "project.json").exists()
        else Bundle.create(path, new_project(path.stem))
    )
    raise typer.Exit(run_desktop(bundle))


@app.command("desktop-check", hidden=True)
def desktop_check(media: Path, output: Path) -> None:
    """Run native Qt checks in a development or packaged runtime."""
    from videoflow.desktop.smoke import main as smoke

    raise typer.Exit(smoke(["--media", str(media), "--output", str(output)]))


@app.command()
def serve(
    project: Annotated[Path, typer.Option(help="Project bundle to open or create.")] = Path(
        "edit.videoflow"
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
        )
    except (OSError, ValueError, ProjectStoreError, ValidationError) as exc:
        typer.echo(f"Export failed: {exc}", err=True)
        raise typer.Exit(1) from exc
    for path in paths:
        typer.echo(str(path.resolve()))
    report = json.loads(paths[-1].read_text(encoding="utf-8"))
    for warning in report["warnings"]:
        typer.echo(f"Warning: {warning}", err=True)
