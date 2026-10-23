"""Audio chunking shared by the ASR adapters (long ranges are cut at quiet points)."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from videoflow.core.time import US_PER_SECOND, TimeRange
from videoflow.engines.protocols import AudioArray

RANGE_PAD_US = 300_000  # 04 S4: ASR runs on VAD ranges padded by 0.3 s
MERGE_GAP_US = 600_000


def plan_chunks(
    n_samples: int,
    sample_rate: int,
    ranges: Sequence[TimeRange] | None,
    *,
    audio: AudioArray | None = None,
    max_s: float = 30.0,
    search_s: float = 3.0,
) -> list[tuple[int, int]]:
    """Sample spans ``(start, end)`` to transcribe, each at most ``max_s`` long.

    With ``ranges`` the spans follow the padded, merged ranges; otherwise the whole input.
    Over-long spans are cut at the quietest 20 ms frame within ``search_s`` of the limit.
    """
    if ranges is None:
        spans = [(0, n_samples)]
    else:
        pad = RANGE_PAD_US
        us = sorted((max(0, r.start_us - pad), r.end_us + pad) for r in ranges)
        merged: list[list[int]] = []
        for s, e in us:
            if merged and s - merged[-1][1] <= MERGE_GAP_US:
                merged[-1][1] = max(merged[-1][1], e)
            else:
                merged.append([s, e])
        spans = [
            (s * sample_rate // US_PER_SECOND, min(n_samples, e * sample_rate // US_PER_SECOND))
            for s, e in merged
        ]
    limit = int(max_s * sample_rate)
    frame = max(1, sample_rate // 50)
    out: list[tuple[int, int]] = []
    for s, e in spans:
        while e - s > limit:
            cut = s + limit
            if audio is not None:
                lo = max(s + limit // 2, cut - int(search_s * sample_rate))
                seg = np.asarray(audio[lo:cut], dtype=np.float32)
                n = len(seg) // frame
                if n > 0:
                    rms = np.sqrt(np.mean(seg[: n * frame].reshape(n, frame) ** 2, axis=1))
                    cut = lo + int(np.argmin(rms)) * frame + frame // 2
            out.append((s, cut))
            s = cut
        if e > s:
            out.append((s, e))
    return out
