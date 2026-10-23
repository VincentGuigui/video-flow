"""Engine interfaces (one implementation each, 08 D-8) and replaying fakes.

Real adapters (WP11) run ONNX / OpenVINO models through ``videoflow.hw.ai`` in worker
processes. Audio is always passed as a 16 kHz mono float32 numpy array (08 §3, 04 S4),
never as a path. Times returned are integer microseconds of the input array's time
(index 0 = 0 us); callers add their own offsets.

The ``Fake*`` engines are deterministic and need no model: they replay fixtures keyed by
:func:`audio_key` / file name, or fall back to simple signal heuristics, so the pipeline
can be tested end to end on synthetic media.
"""

import hashlib
import json
import re
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Literal, Protocol, runtime_checkable

import numpy as np
import numpy.typing as npt

from videoflow.analysis.types import (
    BeatLabelRequest,
    BeatLabelResult,
    EngineInfo,
    LabelTakeOutput,
    Shot,
    Transcript,
    Word,
)
from videoflow.core import ids
from videoflow.core.time import US_PER_SECOND, TimeRange

ASR_SAMPLE_RATE = 16_000

type AudioArray = npt.NDArray[np.float32]
type FrameArray = npt.NDArray[np.uint8]
type Embeddings = npt.NDArray[np.float32]
type TextRole = Literal["query", "passage"]


@runtime_checkable
class VadEngine(Protocol):
    info: EngineInfo

    def speech_ranges(self, audio: AudioArray, sample_rate: int) -> list[TimeRange]: ...


@runtime_checkable
class AsrEngine(Protocol):
    info: EngineInfo

    def transcribe(
        self,
        audio: AudioArray,
        sample_rate: int,
        language: str | None = None,
        ranges: Sequence[TimeRange] | None = None,
    ) -> Transcript:
        """Words with start/end in us; ``prob`` may be None. Only ``ranges`` if given."""
        ...


@runtime_checkable
class TextEmbedder(Protocol):
    info: EngineInfo
    model_id: str
    dim: int

    def encode(self, texts: Sequence[str], role: TextRole = "passage") -> Embeddings:
        """L2-normalised float32 array of shape ``(len(texts), dim)``."""
        ...


@runtime_checkable
class VisualEmbedder(Protocol):
    info: EngineInfo
    model_id: str
    dim: int

    def encode(self, frames: Sequence[FrameArray]) -> Embeddings:
        """L2-normalised embeddings of RGB uint8 frames ``(h, w, 3)``."""
        ...


@runtime_checkable
class ShotDetector(Protocol):
    info: EngineInfo

    def detect(self, video_path: Path, asset_id: str) -> list[Shot]: ...


@runtime_checkable
class LlmLabeler(Protocol):
    info: EngineInfo

    def label(self, request: BeatLabelRequest) -> BeatLabelResult: ...


# --------------------------------------------------------------------------- helpers


def audio_key(audio: AudioArray) -> str:
    """Stable fingerprint of an audio array, used to key fake fixtures."""
    data = np.ascontiguousarray(audio, dtype=np.float32).tobytes()
    return hashlib.blake2b(data, digest_size=8).hexdigest()


def _normalise(rows: npt.NDArray[np.float64]) -> Embeddings:
    norms = np.linalg.norm(rows, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return (rows / norms).astype(np.float32)


def _samples_to_us(index: int, sample_rate: int) -> int:
    return (index * US_PER_SECOND + sample_rate // 2) // sample_rate


# --------------------------------------------------------------------------- fakes


class FakeVadEngine:
    """Replays ranges keyed by :func:`audio_key`, else an RMS-threshold detector."""

    def __init__(
        self,
        responses: Mapping[str, list[TimeRange]] | None = None,
        *,
        threshold: float = 0.01,
        frame_ms: int = 30,
        min_gap_ms: int = 300,
    ) -> None:
        self.info = EngineInfo(engine_id="fake-vad", model_id="rms")
        self.responses = dict(responses or {})
        self.threshold = threshold
        self.frame_ms = frame_ms
        self.min_gap_ms = min_gap_ms
        self.calls = 0

    def speech_ranges(self, audio: AudioArray, sample_rate: int) -> list[TimeRange]:
        self.calls += 1
        key = audio_key(audio)
        if key in self.responses:
            return list(self.responses[key])
        hop = max(1, sample_rate * self.frame_ms // 1000)
        n = len(audio) // hop
        if n == 0:
            return []
        frames = np.asarray(audio[: n * hop], dtype=np.float64).reshape(n, hop)
        active = np.sqrt(np.mean(frames**2, axis=1)) > self.threshold
        ranges: list[TimeRange] = []
        start: int | None = None
        for i, on in enumerate([*active.tolist(), False]):
            if on and start is None:
                start = i
            elif not on and start is not None:
                s_us = _samples_to_us(start * hop, sample_rate)
                e_us = _samples_to_us(i * hop, sample_rate)
                gap_us = self.min_gap_ms * 1000
                if ranges and s_us - ranges[-1].end_us < gap_us:
                    ranges[-1] = TimeRange(start_us=ranges[-1].start_us, end_us=e_us)
                else:
                    ranges.append(TimeRange(start_us=s_us, end_us=e_us))
                start = None
        return ranges


class FakeAsrEngine:
    """Replays transcripts keyed by :func:`audio_key` (or a default one)."""

    def __init__(
        self,
        responses: Mapping[str, Transcript] | None = None,
        *,
        default: Transcript | None = None,
    ) -> None:
        self.info = EngineInfo(engine_id="fake-asr", model_id="fixture")
        self.responses = dict(responses or {})
        self.default = default
        self.calls = 0

    @classmethod
    def from_fixture(cls, path: Path) -> "FakeAsrEngine":
        """JSON file ``{"<audio_key>" | "default": Transcript}``."""
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        default = raw.pop("default", None)
        return cls(
            {k: Transcript.model_validate(v) for k, v in raw.items()},
            default=Transcript.model_validate(default) if default is not None else None,
        )

    def transcribe(
        self,
        audio: AudioArray,
        sample_rate: int,
        language: str | None = None,
        ranges: Sequence[TimeRange] | None = None,
    ) -> Transcript:
        self.calls += 1
        found = self.responses.get(audio_key(audio), self.default)
        if found is None:
            return Transcript(language=language, words=[], engine=self.info)
        words: list[Word] = list(found.words)
        if ranges is not None:
            words = [w for w in words if any(r.start_us <= w.start_us < r.end_us for r in ranges)]
        return found.model_copy(
            update={"words": words, "language": found.language or language, "engine": self.info}
        )


_TOKEN_RE = re.compile(r"\w+", re.UNICODE)


class FakeTextEmbedder:
    """Hashed bag-of-words embedding: cosine follows lexical overlap, deterministic."""

    def __init__(self, dim: int = 384, overrides: Mapping[str, Sequence[float]] | None = None):
        self.dim = dim
        self.model_id = f"fake-bow-{dim}"
        self.info = EngineInfo(engine_id="fake-text-embed", model_id=self.model_id)
        self.overrides = {k: np.asarray(v, dtype=np.float64) for k, v in (overrides or {}).items()}

    def _bucket(self, token: str) -> int:
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=4).digest()
        return int.from_bytes(digest, "big") % self.dim

    def encode(self, texts: Sequence[str], role: TextRole = "passage") -> Embeddings:
        rows = np.zeros((len(texts), self.dim), dtype=np.float64)
        for i, text in enumerate(texts):
            if text in self.overrides:
                rows[i] = self.overrides[text]
                continue
            for token in _TOKEN_RE.findall(text.casefold()):
                rows[i, self._bucket(token)] += 1.0
        return _normalise(rows)


class FakeVisualEmbedder:
    """Coarse colour layout (grid of mean RGB values minus the frame mean), L2-normalised."""

    def __init__(self, grid: int = 8) -> None:
        self.grid = grid
        self.dim = grid * grid * 3
        self.model_id = f"fake-grid-{grid}"
        self.info = EngineInfo(engine_id="fake-visual-embed", model_id=self.model_id)

    def encode(self, frames: Sequence[FrameArray]) -> Embeddings:
        rows = np.zeros((len(frames), self.dim), dtype=np.float64)
        g = self.grid
        for i, frame in enumerate(frames):
            f = np.asarray(frame, dtype=np.float64)
            h, w = f.shape[:2]
            ys = np.linspace(0, h, g + 1).astype(int)
            xs = np.linspace(0, w, g + 1).astype(int)
            cells = [
                f[ys[r] : max(ys[r + 1], ys[r] + 1), xs[c] : max(xs[c + 1], xs[c] + 1)]
                .reshape(-1, f.shape[2] if f.ndim == 3 else 1)
                .mean(axis=0)
                for r in range(g)
                for c in range(g)
            ]
            vec = np.concatenate(cells)
            vec = vec[: self.dim]
            rows[i, : vec.size] = vec - vec.mean()  # exposure-invariant layout
        return _normalise(rows)


class FakeShotDetector:
    """Replays shot boundaries keyed by file name; one shot covering ``duration`` else."""

    def __init__(
        self,
        responses: Mapping[str, Sequence[TimeRange]] | None = None,
        *,
        duration_of: Callable[[Path], int] | None = None,
    ) -> None:
        self.info = EngineInfo(engine_id="fake-shots", model_id="fixture")
        self.responses = {k: list(v) for k, v in (responses or {}).items()}
        self.duration_of = duration_of

    def detect(self, video_path: Path, asset_id: str) -> list[Shot]:
        ranges = self.responses.get(Path(video_path).name)
        if ranges is None:
            if self.duration_of is None:
                return []
            ranges = [TimeRange(start_us=0, end_us=self.duration_of(Path(video_path)))]
        return [
            Shot(
                id=ids.new_id(ids.SHOT),
                asset_id=asset_id,
                index=i,
                start_us=r.start_us,
                end_us=r.end_us,
            )
            for i, r in enumerate(ranges)
        ]


class FakeLlmLabeler:
    """Label = first words of the longest take; best take = longest. No flags."""

    def __init__(self, responses: Mapping[str, BeatLabelResult] | None = None) -> None:
        self.info = EngineInfo(engine_id="fake-llm", model_id="first-words")
        self.responses = dict(responses or {})

    def label(self, request: BeatLabelRequest) -> BeatLabelResult:
        if request.beat_key in self.responses:
            return self.responses[request.beat_key]
        if not request.takes:
            return BeatLabelResult(label="")
        best = max(request.takes, key=lambda t: (t.duration_us, t.take_id))
        label = " ".join(best.text.split()[:6])[:48]
        return BeatLabelResult(
            label=label,
            summary=best.text[:160],
            takes=[LabelTakeOutput(take_id=t.take_id) for t in request.takes],
            best_take_id=best.take_id,
            reason="longest take",
        )
