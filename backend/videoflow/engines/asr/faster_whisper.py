"""faster-whisper (CTranslate2) ASR: optional CPU/CUDA alternative with word probabilities.

Needs the ``whisper`` extra. CTranslate2 has no NPU path, so this adapter only chooses between
CPU and CUDA and does not go through hw.ai (it creates no ONNX sessions). Audio is always a
16 kHz float32 array, never a path (08 §3).
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np

from videoflow.analysis.types import EngineInfo, Transcript, Word
from videoflow.core.time import US_PER_SECOND, TimeRange
from videoflow.engines.asr.chunks import plan_chunks
from videoflow.engines.manifest import fetch
from videoflow.engines.protocols import ASR_SAMPLE_RATE, AudioArray
from videoflow.hw.ai import Prefer

MODEL_KEY = "faster-whisper-tiny"
FILLER_PROMPTS = {
    "fr": "Euh, hum, ben, bah, du coup, voilà, alors euh...",
    "en": "Uh, um, hmm, so, like, you know...",
}
"""Verbatim-style initial prompts that keep disfluencies visible (04 S4)."""


def cuda_available() -> bool:
    try:
        import ctranslate2

        return int(ctranslate2.get_cuda_device_count()) > 0
    except Exception:  # noqa: BLE001 - missing or broken CUDA libs
        return False


class FasterWhisperAsr:
    def __init__(
        self,
        prefer: Prefer = "auto",
        *,
        model_key: str = MODEL_KEY,
        model_dir: str | Path | None = None,
        max_chunk_s: float = 30.0,
    ) -> None:
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise RuntimeError(
                "faster-whisper is not installed (extra: videoflow[whisper])"
            ) from exc
        if model_dir is None:
            model_dir = Path(next(iter(fetch(model_key).values()))).parent
        use_cuda = prefer in ("auto", "gpu", "npu") and cuda_available()
        device = "cuda" if use_cuda else "cpu"
        self._model: Any = WhisperModel(
            str(model_dir), device=device, compute_type="float16" if use_cuda else "int8"
        )
        self.max_chunk_s = max_chunk_s
        self.info = EngineInfo(
            engine_id="faster-whisper", model_id=model_key, device=device if use_cuda else "cpu"
        )

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
        detected = language
        for s, e in spans:
            if e - s < sample_rate // 20:
                continue
            segments, info = self._model.transcribe(
                np.ascontiguousarray(audio[s:e], dtype=np.float32),
                language=language,
                word_timestamps=True,
                condition_on_previous_text=False,
                vad_filter=False,
                initial_prompt=FILLER_PROMPTS.get(language or ""),
            )
            detected = detected or getattr(info, "language", None)
            offset = s * US_PER_SECOND // sample_rate
            words += self._words(segments, offset)
        return Transcript(language=detected, words=words, engine=self.info)

    @staticmethod
    def _words(segments: Any, offset_us: int) -> list[Word]:
        out: list[Word] = []
        for seg in segments:
            for w in seg.words or []:
                start = offset_us + round(w.start * US_PER_SECOND)
                end = offset_us + round(w.end * US_PER_SECOND)
                text = w.word.strip()
                if text:
                    out.append(
                        Word(
                            text=text,
                            start_us=start,
                            end_us=max(end, start + 1),
                            prob=float(w.probability),
                        )
                    )
        return out
