"""Two-pass loudnorm measurement, including digital-silence handling."""

import json
import math
import re
from typing import Any


def measurement(stderr: str) -> dict[str, Any] | None:
    blocks = re.findall(r'\{\s*"input_i".*?\}', stderr, flags=re.DOTALL)
    if not blocks:
        raise ValueError("FFmpeg did not return loudness measurements")
    data: dict[str, Any] = json.loads(blocks[-1])
    if not math.isfinite(float(data["input_i"])):
        return None
    for key in ("input_tp", "input_lra", "input_thresh", "target_offset"):
        if not math.isfinite(float(data[key])):
            raise ValueError(f"Invalid loudness measurement: {key}")
    return data


def measured_filter(data: dict[str, Any], integrated: float, peak: float) -> str:
    return (
        f"loudnorm=I={integrated}:TP={peak}:LRA=11:"
        f"measured_I={data['input_i']}:measured_TP={data['input_tp']}:"
        f"measured_LRA={data['input_lra']}:measured_thresh={data['input_thresh']}:"
        f"offset={data['target_offset']}:linear=true"
    )
