from typer.testing import CliRunner

import videoflow
from videoflow.cli import app


def test_version_command() -> None:
    result = CliRunner().invoke(app, ["version"])
    assert result.exit_code == 0
    assert result.stdout.strip() == videoflow.__version__
