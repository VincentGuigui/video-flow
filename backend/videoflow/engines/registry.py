"""Engine selection: name -> implementation, with lazy imports and runtime availability.

Real adapters need the ``ml`` extra plus one onnxruntime flavour (``whisper`` for
faster-whisper). Importing this module never imports them; ``create`` does, so a missing extra
surfaces as :class:`EngineUnavailableError` naming what to install.
"""

from __future__ import annotations

import importlib.util
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from videoflow.engines import protocols
from videoflow.hw.ai import Prefer

type Kind = Literal["vad", "asr", "text_embed", "visual_embed", "shots"]


class EngineUnavailableError(RuntimeError):
    pass


@dataclass(frozen=True)
class EngineSpec:
    kind: Kind
    name: str
    factory: Callable[[Prefer], Any]
    requires: tuple[str, ...] = ()
    """Importable top-level modules the adapter needs."""
    extra: str | None = None
    """Install hint (pip extra)."""
    ai_device: bool = True
    """True when the adapter honours the NPU -> GPU -> CPU preference."""

    def missing(self) -> list[str]:
        return [m for m in self.requires if importlib.util.find_spec(m) is None]


def _silero(prefer: Prefer) -> Any:
    from videoflow.engines.vad.silero_onnx import SileroVad

    return SileroVad(prefer)


def _parakeet(prefer: Prefer) -> Any:
    from videoflow.engines.asr.parakeet_onnx import ParakeetOnnxAsr

    return ParakeetOnnxAsr(prefer)


def _faster_whisper(prefer: Prefer) -> Any:
    from videoflow.engines.asr.faster_whisper import FasterWhisperAsr

    return FasterWhisperAsr(prefer)


def _minilm(prefer: Prefer) -> Any:
    from videoflow.engines.embed.onnx_st import OnnxTextEmbedder

    return OnnxTextEmbedder("paraphrase-multilingual-minilm-l12-v2", prefer)


def _phash(_: Prefer) -> Any:
    from videoflow.engines.vision.phash_hist import PhashHistEmbedder

    return PhashHistEmbedder()


def _dinov2(prefer: Prefer) -> Any:
    from videoflow.engines.vision.dinov2_onnx import Dinov2OnnxEmbedder

    return Dinov2OnnxEmbedder(prefer)


def _scenedetect(_: Prefer) -> Any:
    from videoflow.analysis.shots import SceneDetectShots

    return SceneDetectShots()


_ORT = ("onnxruntime",)
_ML = "ml"

_SPECS: tuple[EngineSpec, ...] = (
    EngineSpec("vad", "silero", _silero, (*_ORT, "huggingface_hub"), _ML),
    EngineSpec("vad", "fake", lambda _: protocols.FakeVadEngine(), ai_device=False),
    EngineSpec("asr", "parakeet", _parakeet, (*_ORT, "onnx_asr", "huggingface_hub"), _ML),
    EngineSpec(
        "asr",
        "faster-whisper",
        _faster_whisper,
        ("faster_whisper", "huggingface_hub"),
        "whisper",
        ai_device=False,
    ),  # fmt: skip
    EngineSpec("asr", "fake", lambda _: protocols.FakeAsrEngine(), ai_device=False),
    EngineSpec("text_embed", "minilm", _minilm, (*_ORT, "tokenizers", "huggingface_hub"), _ML),
    EngineSpec("text_embed", "fake", lambda _: protocols.FakeTextEmbedder(), ai_device=False),
    EngineSpec("visual_embed", "phash-hist", _phash, (), None, ai_device=False),
    EngineSpec("visual_embed", "dinov2", _dinov2, (*_ORT, "cv2", "huggingface_hub"), _ML),
    EngineSpec("visual_embed", "fake", lambda _: protocols.FakeVisualEmbedder(), ai_device=False),
    EngineSpec("shots", "scenedetect", _scenedetect, ("scenedetect", "cv2"), _ML, ai_device=False),
    EngineSpec("shots", "fake", lambda _: protocols.FakeShotDetector(), ai_device=False),
)

REGISTRY: dict[tuple[str, str], EngineSpec] = {(s.kind, s.name): s for s in _SPECS}

DEFAULTS: dict[Kind, str] = {
    "vad": "silero",
    "asr": "parakeet",
    "text_embed": "minilm",
    "visual_embed": "dinov2",
    "shots": "scenedetect",
}


def names(kind: Kind) -> list[str]:
    return [s.name for s in _SPECS if s.kind == kind]


def available(kind: Kind) -> list[str]:
    """Engines of ``kind`` whose Python dependencies are importable here."""
    return [s.name for s in _SPECS if s.kind == kind and not s.missing()]


def create(kind: Kind, name: str | None = None, *, prefer: Prefer = "auto") -> Any:
    """Instantiate engine ``name`` (default per kind). ``prefer`` is the AI device preference."""
    name = name or DEFAULTS[kind]
    try:
        spec = REGISTRY[(kind, name)]
    except KeyError:
        raise KeyError(f"unknown {kind} engine {name!r}; known: {names(kind)}") from None
    missing = spec.missing()
    if missing:
        hint = f" (install videoflow[{spec.extra}])" if spec.extra else ""
        raise EngineUnavailableError(f"{kind}/{name} needs {', '.join(missing)}{hint}")
    return spec.factory(prefer)
