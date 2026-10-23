"""Doctor data: FFmpeg capabilities, video acceleration and AI providers in one structure."""

from __future__ import annotations

import platform
import sys
from pathlib import Path
from typing import Any

from videoflow.hw import ai, video
from videoflow.media.caps import FFmpegCaps, locate_binaries, probe_caps


def build_report(
    caps: FFmpegCaps | None = None,
    *,
    ffmpeg: Path | str | None = None,
    ai_prefer: ai.Prefer = "auto",
    test_video_hw: bool = True,
) -> dict[str, Any]:
    """Collect everything `videoflow doctor` prints. Missing parts are reported, not raised."""
    report: dict[str, Any] = {
        "platform": {
            "system": platform.system(),
            "machine": platform.machine(),
            "python": sys.version.split()[0],
        }
    }
    try:
        caps = caps or probe_caps(locate_binaries(ffmpeg=ffmpeg))
    except (FileNotFoundError, RuntimeError) as exc:
        report["ffmpeg"] = {"error": str(exc)}
        report["video"] = None
    else:
        report["ffmpeg"] = caps.to_dict()
        if test_video_hw:
            hw = video.probe_video_hw(caps)
            report["video"] = {
                **hw.to_dict(),
                "encoder": video.choose_encoder(hw).encoder,
                "decoder": d.hwaccel if (d := video.choose_decoder(hw)) else None,
            }
        else:
            report["video"] = None
    info = ai.describe_ai()
    chain = ai.probe_chain(ai_prefer)
    report["ai"] = {
        **info,
        "requested": ai_prefer,
        "selected": chain[0].label if chain else None,
        "selected_device": chain[0].device.value if chain else None,
    }
    return report


def format_report(report: dict[str, Any]) -> str:
    lines: list[str] = []
    p = report["platform"]
    lines.append(f"Platform: {p['system']} {p['machine']}, Python {p['python']}")
    ff = report["ffmpeg"]
    if "error" in ff:
        lines.append(f"FFmpeg: NOT FOUND ({ff['error']})")
    else:
        lines.append(f"FFmpeg: {ff['version']} at {ff['ffmpeg']}")
        lines.append(
            f"  graph flag: {ff['graph_flag']}, xfade transitions: {len(ff['xfade_transitions'])}"
        )
    v = report.get("video")
    if v:
        lines.append(f"Video encode: {v['encoder']}  decode: {v['decoder'] or 'software'}")
        if v["failed"]:
            lines.append(f"  listed but failing: {', '.join(v['failed'])}")
    a = report["ai"]
    if a["onnxruntime"] is None:
        lines.append("AI: onnxruntime not installed")
    else:
        lines.append(f"AI: onnxruntime {a['onnxruntime']}, providers {', '.join(a['providers'])}")
        lines.append(f"  selected: {a['selected']} ({a['selected_device']}), mode {a['requested']}")
    return "\n".join(lines)
