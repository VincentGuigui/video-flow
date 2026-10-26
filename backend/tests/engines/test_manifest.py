from __future__ import annotations

import re
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from videoflow.engines import manifest as mf

PREFIXES = ("videoflow/engines", "videoflow/analysis")
ROOT = Path(__file__).resolve().parents[2]


def test_shipped_manifest_is_pinned_and_open():
    man = mf.load_manifest()
    assert {"silero-vad", "parakeet-tdt-0.6b-v3-int8", "multilingual-e5-small"} <= set(man.models)
    for key, spec in man.models.items():
        man.get(key)  # raises when gated, unpinned or not permissively licensed
        assert re.fullmatch(r"[0-9a-f]{40}", spec.revision), key
        assert spec.files
        assert not spec.gated


def test_e5_has_query_prefix_and_dim():
    spec = mf.load_manifest().get("multilingual-e5-small")
    assert spec.query_prefix == "query: "
    assert spec.dim == 384


BASE = """
[policy]
allowed_licenses = ["mit"]
[models.m]
purpose = "vad"
repo = "o/r"
revision = "{rev}"
license = "{lic}"
gated = {gated}
files = ["a.onnx"]
"""


def parse(rev="a" * 40, lic="mit", gated="false"):
    return mf.parse_manifest(BASE.format(rev=rev, lic=lic, gated=gated))


def test_gated_model_refused():
    with pytest.raises(mf.ModelRefusedError, match="gated"):
        parse(gated="true").get("m")


def test_non_permissive_licence_refused():
    with pytest.raises(mf.ModelRefusedError, match="licence"):
        parse(lic="cc-by-nc-4.0").get("m")


def test_branch_revision_refused():
    with pytest.raises(mf.ModelRefusedError, match="revision"):
        parse(rev="main").get("m")


def test_unknown_model():
    with pytest.raises(KeyError):
        parse().get("nope")


def test_fetch_refuses_before_any_download(monkeypatch):
    pytest.importorskip("huggingface_hub")  # `ml` extra
    called = []
    import huggingface_hub

    monkeypatch.setattr(huggingface_hub, "hf_hub_download", lambda *a, **k: called.append(a))
    with pytest.raises(mf.ModelRefusedError):
        mf.fetch("m", parse(gated="true"))
    assert not called


def test_fetch_maps_hub_gated_error(monkeypatch):
    pytest.importorskip("huggingface_hub")  # `ml` extra
    import huggingface_hub
    from huggingface_hub.errors import GatedRepoError

    def boom(*a, **k):
        raise GatedRepoError("gated", response=MagicMock(headers={}))

    monkeypatch.setattr(huggingface_hub, "hf_hub_download", boom)
    with pytest.raises(mf.ModelRefusedError, match="gated"):
        mf.fetch("m", parse())


def test_fetch_passes_pinned_revision(monkeypatch, tmp_path):
    pytest.importorskip("huggingface_hub")  # `ml` extra
    import huggingface_hub

    seen = {}

    def fake(repo, name, revision=None, cache_dir=None):
        seen.update(repo=repo, name=name, revision=revision)
        return str(tmp_path / name)

    monkeypatch.setattr(huggingface_hub, "hf_hub_download", fake)
    out = mf.fetch("m", parse())
    assert seen == {"repo": "o/r", "name": "a.onnx", "revision": "a" * 40}
    assert out == {"a.onnx": tmp_path / "a.onnx"}


def test_models_dir_is_always_application_models(monkeypatch, tmp_path):
    from videoflow import runtime
    monkeypatch.setattr(runtime, "application_dir", lambda: tmp_path)
    monkeypatch.setenv("VIDEOFLOW_MODELS_DIR", "ignored-external-directory")
    assert mf.models_dir() == tmp_path / "models"
    assert __import__("os").environ["VIDEOFLOW_MODELS_DIR"] == str(tmp_path / "models")


def test_all_onnx_sessions_go_through_make_session():
    """No adapter may build an InferenceSession itself (NPU -> GPU -> CPU lives in hw.ai)."""
    offenders = []
    for prefix in PREFIXES:
        for path in (ROOT / prefix).rglob("*.py"):
            if "InferenceSession(" in path.read_text(encoding="utf-8"):
                offenders.append(str(path.relative_to(ROOT)))
    assert offenders == []
