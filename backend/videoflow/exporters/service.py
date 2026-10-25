"""File export entry point shared by the CLI and future API."""

import json
from collections.abc import Sequence
from pathlib import Path

from videoflow.exporters.edl import export_edl
from videoflow.exporters.otio_compile import compile_timeline, serialize
from videoflow.exporters.otioz import write_otioz
from videoflow.exporters.paper_edit import export_csv, export_markdown
from videoflow.exporters.srt import export_srt
from videoflow.exporters.transcript import Transcripts
from videoflow.project.models import Project
from videoflow.project.store import save_atomic
from videoflow.timeline.resolve import resolve

FORMATS = frozenset({"otio", "otioz", "edl", "srt", "paper-edit"})


def export_project(
    project: Project,
    destination: Path,
    formats: Sequence[str] = ("otio",),
    *,
    transcripts: Transcripts | None = None,
    include_alternates: bool = False,
    overwrite: bool = False,
) -> list[Path]:
    """Write edit.* files plus a report describing losses and resolver warnings."""
    unknown = set(formats) - FORMATS
    if unknown:
        raise ValueError(f"Unknown export formats: {', '.join(sorted(unknown))}")
    if not formats:
        raise ValueError("Select at least one export format")
    if "srt" in formats and transcripts is None:
        raise ValueError("SRT requires transcripts (pass --transcripts)")
    resolved = resolve(project)
    warnings = [f"{w.code}: {w.message}" for w in resolved.warnings]
    if any(f in formats for f in ("otio", "otioz")):
        warnings.append("OTIO gain, fades, fit and freeze handles are metadata only.")
    if "paper-edit" in formats and transcripts is None:
        warnings.append("No transcripts provided; paper edit transcript cells are empty.")
    texts: dict[str, str] = {}
    compiled = None
    if "otio" in formats or "otioz" in formats:
        compiled = compile_timeline(resolved, project, include_alternates=include_alternates)
    if "otio" in formats:
        texts["edit.otio"] = serialize(compiled)
    if "edl" in formats:
        edl = export_edl(resolved, project)
        texts["edit.edl"] = edl.text
        texts["edit.reels.json"] = json.dumps(edl.reels, ensure_ascii=False, indent=2) + "\n"
        warnings.extend(edl.warnings)
    if "srt" in formats:
        texts["edit.srt"] = export_srt(resolved, project, transcripts or {})
        if not texts["edit.srt"]:
            warnings.append("No audible transcript words fall inside the edit; SRT is empty.")
    if "paper-edit" in formats:
        texts["edit.md"] = export_markdown(resolved, project, transcripts or {})
        texts["edit.csv"] = export_csv(resolved, project, transcripts or {})
    names = [*texts, *(["edit.otioz"] if "otioz" in formats else []), "edit.report.json"]
    texts["edit.report.json"] = (
        json.dumps(
            {
                "projectId": project.id,
                "revision": project.revision,
                "rate": resolved.rate.dump(),
                "durationFrames": resolved.duration,
                "formats": sorted(set(formats)),
                "files": names,
                "warnings": warnings,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    )
    destination = Path(destination)
    if not overwrite:
        for name in names:
            if (destination / name).exists():
                raise FileExistsError(
                    f"Export already exists: {destination / name}; use --overwrite"
                )
    destination.mkdir(parents=True, exist_ok=True)
    # Validate and package media before publishing the text outputs.
    if "otioz" in formats:
        write_otioz(compiled, destination / "edit.otioz")
    for name, content in texts.items():
        save_atomic(destination / name, content.encode("utf-8"))
    return [destination / name for name in names]
