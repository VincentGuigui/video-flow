"""Portable OTIOZ archives, with collision-free media names and atomic publication."""

import os
import uuid
import zipfile
from pathlib import Path
from typing import Any

import opentimelineio as otio

from videoflow.exporters.otio_compile import serialize


def write_otioz(timeline: Any, destination: Path) -> None:
    """Bundle referenced files once, preserving clips with identical source basenames.

    Fails before publication if a referenced file is absent. The input is never relinked.
    """
    result = timeline.deepcopy()
    files: dict[Path, str] = {}
    for clip in result.find_clips():
        ref = clip.media_reference
        if not isinstance(ref, otio.schema.ExternalReference):
            raise ValueError(f"Cannot bundle missing media for {clip.name}")
        path = Path(otio.url_utils.filepath_from_url(ref.target_url)).resolve()
        if not path.is_file():
            raise FileNotFoundError(f"Cannot bundle missing media: {path}")
        if path not in files:
            files[path] = f"media/{len(files) + 1:04d}_{path.name}"
        ref.target_url = otio.url_utils.url_from_filepath(files[path])
    destination = Path(destination)
    temp = destination.with_name(f".{destination.name}.{uuid.uuid4().hex}.tmp")
    try:
        with zipfile.ZipFile(temp, "w") as archive:
            archive.writestr("version.txt", "1.0.0", compress_type=zipfile.ZIP_DEFLATED)
            archive.writestr("content.otio", serialize(result), compress_type=zipfile.ZIP_DEFLATED)
            for source, name in files.items():
                archive.write(source, name, compress_type=zipfile.ZIP_STORED)
        os.replace(temp, destination)
    finally:
        temp.unlink(missing_ok=True)
