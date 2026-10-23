"""Command line entry point (`videoflow`). Commands are added by later work packages."""

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
