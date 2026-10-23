"""Parakeet TDT 0.6B v3 (int8 ONNX) through onnx-asr, sessions created by hw.ai.

onnx-asr builds its own ``InferenceSession`` objects; the module-level ``rt`` of its NeMo
adapter is swapped for the duration of construction so that every session goes through
:func:`videoflow.hw.ai.make_session` (NPU -> GPU -> CPU, per model). The encoder follows the
requested device preference; the dynamic decoder/joint loop is pinned to the CPU (08 §0.1).
"""

from __future__ import annotations

import importlib
import types
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import numpy as np

from videoflow.analysis.types import EngineInfo, Transcript, Word
from videoflow.core.time import US_PER_SECOND, TimeRange
from videoflow.engines.asr.chunks import plan_chunks
from videoflow.engines.manifest import fetch
from videoflow.engines.protocols import ASR_SAMPLE_RATE, AudioArray
from videoflow.hw.ai import Device, Prefer, make_session

MODEL_KEY = "parakeet-tdt-0.6b-v3-int8"
MAX_TAIL_US = 600_000
"""A word never extends more than this past its last token (silence follows the last word)."""


def tokens_to_words(
    tokens: Sequence[str],
    times_s: Sequence[float],
    *,
    offset_us: int = 0,
    end_cap_us: int | None = None,
) -> list[Word]:
    """Merge SentencePiece tokens into words (08 §3, 04 S4).

    A token starting with a space opens a word. A word starts at its first token and ends at
    the start of the next word's first token, at most ``MAX_TAIL_US`` after its own last token
    and never beyond ``end_cap_us`` (the speech range / chunk end). ``prob`` stays None.
    """
    groups: list[list[int]] = []
    for i, tok in enumerate(tokens):
        if tok.startswith(" ") or not groups:
            groups.append([i])
        else:
            groups[-1].append(i)
    words: list[Word] = []
    for g, idxs in enumerate(groups):
        text = "".join(tokens[i] for i in idxs).strip()
        if not text:
            continue
        start = offset_us + round(times_s[idxs[0]] * US_PER_SECOND)
        last_start = offset_us + round(times_s[idxs[-1]] * US_PER_SECOND)
        end = last_start + MAX_TAIL_US
        if g + 1 < len(groups):
            end = min(end, offset_us + round(times_s[groups[g + 1][0]] * US_PER_SECOND))
        if end_cap_us is not None:
            end = min(end, end_cap_us)
        words.append(Word(text=text, start_us=start, end_us=max(end, start + 1)))
    return words


@contextmanager
def _routed_sessions(prefer: Prefer, devices: dict[str, Device]) -> Iterator[None]:
    """Make onnx-asr's NeMo adapter create its sessions via ``make_session``."""
    nemo: Any = importlib.import_module("onnx_asr.models.nemo")

    real_rt = nemo.rt

    def factory(path: str | Path, **_: Any) -> Any:
        is_decoder = "decoder" in Path(path).name
        ms = make_session(path, "cpu" if is_decoder else prefer)
        devices["decoder" if is_decoder else "encoder"] = ms.device
        return ms.session

    proxy = types.SimpleNamespace(**{k: getattr(real_rt, k) for k in dir(real_rt)})
    proxy.InferenceSession = factory
    nemo.rt = proxy
    try:
        yield
    finally:
        nemo.rt = real_rt


class ParakeetOnnxAsr:
    """Multilingual (incl. FR/EN) ASR with native token timestamps; no word probabilities."""

    def __init__(self, prefer: Prefer = "auto", *, max_chunk_s: float = 30.0) -> None:
        from onnx_asr.models.nemo import NemoConformerTdt
        from onnx_asr.preprocessors.numpy_preprocessor import NemoPreprocessorNumpy

        files = fetch(MODEL_KEY)
        by_name = {Path(k).name: v for k, v in files.items()}
        model_files = {
            "encoder": by_name["encoder-model.int8.onnx"],
            "decoder_joint": by_name["decoder_joint-model.int8.onnx"],
            "vocab": by_name["vocab.txt"],
            "config": by_name["config.json"],
        }
        devices: dict[str, Device] = {}
        with _routed_sessions(prefer, devices):
            self._asr = NemoConformerTdt(
                model_files,
                NemoPreprocessorNumpy,
                {"providers": ["CPUExecutionProvider"]},
            )
        self.max_chunk_s = max_chunk_s
        self.info = EngineInfo(
            engine_id="parakeet-onnx",
            model_id=MODEL_KEY,
            device=devices.get("encoder", Device.CPU).value,
        )

    def _recognize(self, chunk: AudioArray) -> tuple[list[str], list[float]]:
        x = np.asarray(chunk, dtype=np.float32)[None, :]
        lens = np.array([x.shape[1]], dtype=np.int64)
        res = next(iter(self._asr.recognize_batch(x, lens)))
        return list(res.tokens or []), list(res.timestamps or [])

    def transcribe(
        self,
        audio: AudioArray,
        sample_rate: int,
        language: str | None = None,
        ranges: Sequence[TimeRange] | None = None,
    ) -> Transcript:
        if sample_rate != ASR_SAMPLE_RATE:
            raise ValueError(f"expected {ASR_SAMPLE_RATE} Hz audio, got {sample_rate}")
        spans = plan_chunks(len(audio), sample_rate, ranges, audio=audio, max_s=self.max_chunk_s)
        words: list[Word] = []
        for s, e in spans:
            if e - s < sample_rate // 20:
                continue
            tokens, times = self._recognize(audio[s:e])
            offset = s * US_PER_SECOND // sample_rate
            cap = e * US_PER_SECOND // sample_rate
            words += tokens_to_words(tokens, times, offset_us=offset, end_cap_us=cap)
        return Transcript(language=language, words=words, engine=self.info)
