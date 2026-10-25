"""Command line entry point (``videoflow``)."""

import json
from pathlib import Path
from typing import Annotated

import typer

from videoflow import __version__

app = typer.Typer(no_args_is_help=True, help="Video-Flow command line.")


@app.callback()
def main() -> None:
    """Video-Flow command line."""


@app.command()
def version() -> None:
    """Print the Video-Flow version."""
    typer.echo(__version__)


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
