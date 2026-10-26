"""Source-adjacent analysis files and killable real transcription workers."""

import contextlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
from pydantic import Field
from rapidfuzz.fuzz import token_set_ratio

from videoflow.analysis.types import Transcript, Word
from videoflow.core.base import CamelModel
from videoflow.editor.topics import Topic, detect_topics, extractive_summary
from videoflow.engines.registry import create
from videoflow.project.store import Bundle, save_atomic

if TYPE_CHECKING:
    from videoflow.engines.summary import QwenSummary


class AnalysisFile(CamelModel):
    version: int = 1
    source_hash: str | None = None
    words: list[Word] = Field(default_factory=list)
    summary: str = ""
    keywords: list[str] = Field(default_factory=list)
    language: str | None = None
    summary_engine: str = "deterministic"
    summary_scope: str = "full transcript"
    topics: list[Topic] = Field(default_factory=list)
    topics_engine: str = "deterministic"


def with_topics(analysis: AnalysisFile) -> AnalysisFile:
    """Older sidecars have no topics; derive them without rewriting the file."""
    if analysis.words and not analysis.topics:
        analysis.topics = detect_topics(analysis.words)
    return analysis


def sidecar_path(source: Path) -> Path:
    return source.with_suffix(".json")


def read_sidecar(source: Path, digest: str) -> AnalysisFile | None:
    for path in (sidecar_path(source), Path(str(source) + ".json")):
        if not path.is_file():
            continue
        with contextlib.suppress(ValueError, OSError):
            raw = json.loads(path.read_bytes())
            if not isinstance(raw, dict) or "words" not in raw:
                continue
            analysis = AnalysisFile.model_validate(raw)
            if analysis.version == 1 and analysis.source_hash in (None, digest):
                return with_topics(analysis)
    return None


def cached_path(bundle: Bundle, digest: str) -> Path:
    # Asset fingerprints are opaque; hash again to guarantee a filename-safe cache key.
    import hashlib

    return (
        bundle.analysis_dir / "sidecars" / (hashlib.sha256(digest.encode()).hexdigest() + ".json")
    )


def load_analysis(source: Path, digest: str, bundle: Bundle) -> AnalysisFile | None:
    result = read_sidecar(source, digest)
    if result is not None:
        return result
    path = cached_path(bundle, digest)
    if path.is_file():
        with contextlib.suppress(ValueError, OSError):
            analysis = AnalysisFile.model_validate_json(path.read_bytes())
            if analysis.source_hash == digest and analysis.version == 1:
                return with_topics(analysis)
    return None


def store_analysis(source: Path, analysis: AnalysisFile, bundle: Bundle) -> tuple[Path, str | None]:
    """Always cache first, then attempt a non-overwriting source-adjacent sidecar."""
    cache = cached_path(bundle, analysis.source_hash or "")
    cache.parent.mkdir(parents=True, exist_ok=True)
    save_atomic(cache, (json.dumps(analysis.dump(), ensure_ascii=False, indent=2) + "\n").encode())
    try:
        write_sidecar(source, analysis)
        return sidecar_path(source), None
    except OSError as exc:
        return (
            cache,
            f"Analysis ready; sidecar could not be saved beside source ({exc}). Cached at {cache}",
        )


def describe(transcript: Transcript, digest: str) -> AnalysisFile:
    text = " ".join(w.text for w in transcript.words)
    stop = {"the", "and", "this", "that", "with", "les", "des", "une", "dans", "pour", "est"}
    tokens = [
        s.casefold() for s in re.findall(r"\w+", text) if len(s) > 3 and s.casefold() not in stop
    ]
    return AnalysisFile(
        source_hash=digest,
        words=transcript.words,
        language=transcript.language,
        summary=extractive_summary(transcript.words),
        keywords=[t for t, _ in Counter(tokens).most_common(12)],
        topics=detect_topics(transcript.words),
    )


def write_sidecar(source: Path, analysis: AnalysisFile) -> None:
    target = sidecar_path(source)
    if target.exists():
        raise FileExistsError(f"Will not overwrite existing analysis: {target}")
    save_atomic(target, (json.dumps(analysis.dump(), ensure_ascii=False, indent=2) + "\n").encode())


def similar(a: AnalysisFile, b: AnalysisFile) -> bool:
    first = " ".join(w.text for w in a.words).strip()
    second = " ".join(w.text for w in b.words).strip()
    if len(first.split()) < 4 or len(second.split()) < 4:
        return False
    keywords_a, keywords_b = set(a.keywords), set(b.keywords)
    overlap = len(keywords_a & keywords_b) / max(1, len(keywords_a | keywords_b))
    return token_set_ratio(first.casefold(), second.casefold()) >= 85 and overlap >= 0.35


class Transcriber:
    """Factory lives at module scope so multiprocessing spawn can import it."""

    def __init__(self, asr_engine: str = "parakeet", prefer: str = "auto") -> None:
        self.vad = create("vad", prefer=prefer)
        self.asr = create("asr", asr_engine, prefer=prefer)
        self.summary: QwenSummary | None = None

    def _qwen(self) -> "QwenSummary":
        if self.summary is None:
            from videoflow.engines.summary import QwenSummary

            self.summary = QwenSummary()
        return self.summary

    def summarize(self, text: str) -> tuple[str, list[str]]:
        return self._qwen().describe(text)

    def topics(self, words: list[Word]) -> list[Topic]:
        """Topic sections titled by local Qwen, with keyword titles as fallback."""
        return detect_topics(words, title=self._qwen().title)

    def transcribe(self, pcm: bytes, language: str) -> Transcript:
        audio = np.frombuffer(pcm, dtype="<f4").copy()
        ranges = self.vad.speech_ranges(audio, 16000)
        result: Transcript = self.asr.transcribe(audio, 16000, language=language, ranges=ranges)
        return result
