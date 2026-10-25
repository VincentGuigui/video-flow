import json
import zipfile

import opentimelineio as otio
import pytest
from typer.testing import CliRunner

from tests.timeline.builders import ProjectBuilder, S, clip
from videoflow.analysis.types import Transcript, Word
from videoflow.cli import app
from videoflow.exporters.service import export_project
from videoflow.project.store import Bundle


@pytest.fixture
def bundle(tmp_path):
    b = ProjectBuilder().asset("a", 10 * S).beat("beat", clip("c", "a", S, 3 * S))
    project = b.build()
    return Bundle.create(tmp_path / "test.videoflow", project)


def test_export_cli_writes_all_text_formats_and_reports_losses(bundle, tmp_path):
    transcript_file = tmp_path / "words.json"
    transcript_file.write_text(
        json.dumps(
            {
                "a": Transcript(
                    words=[Word(text="Bonjour.", start_us=1_200_000, end_us=1_700_000)]
                ).dump()
            }
        ),
        encoding="utf-8",
    )
    original = bundle.project_file.read_bytes()
    result = CliRunner().invoke(
        app,
        [
            "export",
            str(bundle.path),
            "--otio",
            "--edl",
            "--srt",
            "--paper-edit",
            "--transcripts",
            str(transcript_file),
        ],
    )
    assert result.exit_code == 0, result.output
    report = json.loads((bundle.exports_dir / "edit.report.json").read_text(encoding="utf-8"))
    assert report["durationFrames"] == 60
    assert len(report["files"]) == 7
    assert report["warnings"]
    assert "Bonjour." in (bundle.exports_dir / "edit.srt").read_text(encoding="utf-8")
    timeline = otio.adapters.read_from_file(str(bundle.exports_dir / "edit.otio"))
    assert timeline.duration().value == 60
    assert bundle.project_file.read_bytes() == original


def test_default_format_file_input_and_overwrite(bundle):
    runner = CliRunner()
    args = ["export", str(bundle.project_file)]
    assert runner.invoke(app, args).exit_code == 0
    original = (bundle.exports_dir / "edit.otio").read_bytes()
    result = runner.invoke(app, args)
    assert result.exit_code == 1
    assert "--overwrite" in result.output
    assert (bundle.exports_dir / "edit.otio").read_bytes() == original
    assert runner.invoke(app, args + ["--overwrite"]).exit_code == 0


@pytest.mark.parametrize(
    "arguments,message",
    [
        (["--srt"], "requires transcripts"),
        (["--otioz"], "missing media"),
    ],
)
def test_failed_export_leaves_no_published_files(bundle, arguments, message):
    result = CliRunner().invoke(app, ["export", str(bundle.path), *arguments])
    assert result.exit_code == 1
    assert message in result.output
    assert not list(bundle.exports_dir.iterdir())


def test_invalid_transcript_input_is_readable_error(bundle, tmp_path):
    words = tmp_path / "words.json"
    words.write_text("[]", encoding="utf-8")
    result = CliRunner().invoke(
        app, ["export", str(bundle.path), "--srt", "--transcripts", str(words)]
    )
    assert result.exit_code == 1
    assert "Export failed:" in result.output
    assert not list(bundle.exports_dir.iterdir())


def test_export_rejects_unknown_formats_and_preserves_existing_outputs(bundle):
    with pytest.raises(ValueError, match="Unknown export formats"):
        export_project(bundle.project, bundle.exports_dir, ["fcpxml"])
    assert not list(bundle.exports_dir.iterdir())
    existing = bundle.exports_dir / "edit.csv"
    existing.write_text("keep me", encoding="utf-8")
    with pytest.raises(FileExistsError):
        export_project(bundle.project, bundle.exports_dir, ["otio", "paper-edit"])
    assert existing.read_text(encoding="utf-8") == "keep me"
    assert not (bundle.exports_dir / "edit.otio").exists()


def test_otioz_bundles_generated_sample(bundle, samples_dir):
    media = next(samples_dir.glob("*.mp4"))
    project = bundle.project.model_copy(deep=True)
    project.assets[0].path = str(media)
    paths = export_project(project, bundle.exports_dir, ["otioz"])
    with zipfile.ZipFile(paths[0]) as archive:
        assert archive.read(f"media/0001_{media.name}") == media.read_bytes()
    assert otio.adapters.read_from_file(str(paths[0])).duration().value == 60
