"""Errors shared by the media service modules."""

from __future__ import annotations


class MediaError(RuntimeError):
    """An FFmpeg-based media step failed. `detail` holds the stderr tail."""

    def __init__(self, message: str, detail: str = "") -> None:
        super().__init__(f"{message}: {detail.strip()[-400:]}" if detail else message)
        self.detail = detail


class MediaCancelled(RuntimeError):
    """The step was cancelled through its cancel event; no partial output is left behind."""
