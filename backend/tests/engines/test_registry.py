from __future__ import annotations

import pytest

from videoflow.engines import protocols, registry


def test_fakes_are_selectable_and_satisfy_protocols():
    assert isinstance(registry.create("vad", "fake"), protocols.VadEngine)
    assert isinstance(registry.create("asr", "fake"), protocols.AsrEngine)
    assert isinstance(registry.create("text_embed", "fake"), protocols.TextEmbedder)
    assert isinstance(registry.create("visual_embed", "fake"), protocols.VisualEmbedder)
    assert isinstance(registry.create("shots", "fake"), protocols.ShotDetector)


def test_unknown_engine():
    with pytest.raises(KeyError, match="known"):
        registry.create("asr", "nope")


def test_defaults_exist():
    for kind, name in registry.DEFAULTS.items():
        assert name in registry.names(kind)


def test_phash_has_no_dependencies():
    assert "phash-hist" in registry.available("visual_embed")
    assert registry.create("visual_embed", "phash-hist").dim == 112


def test_missing_dependency_is_reported(monkeypatch):
    spec = registry.REGISTRY[("asr", "faster-whisper")]
    monkeypatch.setattr(type(spec), "missing", lambda self: ["faster_whisper"])
    assert "faster-whisper" not in registry.available("asr")
    with pytest.raises(registry.EngineUnavailableError, match=r"videoflow\[whisper\]"):
        registry.create("asr", "faster-whisper")


def test_prefer_is_forwarded(monkeypatch):
    seen = []
    spec = registry.REGISTRY[("vad", "silero")]
    patched = registry.EngineSpec(spec.kind, spec.name, lambda p: seen.append(p) or "x")
    monkeypatch.setitem(registry.REGISTRY, ("vad", "silero"), patched)
    assert registry.create("vad", prefer="cpu") == "x"
    assert seen == ["cpu"]
