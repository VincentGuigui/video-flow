import json
import wave
from pathlib import Path

import numpy as np
import pytest

from videoflow.analysis.types import Word
from videoflow.editor import grouping as g
from videoflow.editor.analysis import AnalysisFile

PAIRS = json.loads((Path(__file__).parents[1] / "fixtures" / "retake_pairs.json").read_text())
TAKE = [
    "Dans la boîte on trouve le câble USB-C et le chargeur 65 watts.",
    "La batterie tient une journée.",
]
RETAKE = [
    "Euh dans la boîte on a le câble USB-C et un chargeur de 65 watts.",
    "La batterie tient une journée complète.",
]
OTHER = ["Le prix de lancement est de 899 euros.", "Il sera disponible en magasin le 15 novembre."]


def clip(key, texts, vectors=None):
    return g.ClipText(key, texts, vectors)


def test_lexical_coverage_groups_retakes_and_not_other_sentences():
    assert g.retake_score(clip("a", RETAKE), clip("b", TAKE)) == 1.0
    assert g.retake_score(clip("a", OTHER), clip("b", TAKE)) == 0.0
    assert g.best_match(clip("new", RETAKE), [clip("x", OTHER), clip("y", TAKE)]) == ("y", 1.0)
    assert g.best_match(clip("new", OTHER), [clip("y", TAKE)]) is None


def test_partial_retake_matches_in_either_direction():
    assert g.retake_score(clip("a", RETAKE[:1]), clip("b", TAKE + OTHER)) == 1.0


def test_vectors_blend_with_word_overlap():
    # Orthogonal vectors make the blend reject a lexical-only borderline match.
    a = clip("a", ["la batterie tient bien"], np.array([[1.0, 0.0]], dtype=np.float32))
    b = clip("b", ["la batterie tient mal"], np.array([[0.0, 1.0]], dtype=np.float32))
    assert g.coverage(a, b) == 0.0
    assert g.coverage(clip("a", a.texts), clip("b", b.texts)) == 1.0


def test_vector_cache_round_trip_checks_sentence_count(tmp_path):
    path = g.vectors_path(tmp_path, "digest")
    path.parent.mkdir(parents=True)
    path.write_bytes(g.encode_vectors(np.eye(2, 384, dtype=np.float32)))
    assert g.read_vectors(path, 2).shape == (2, 384)
    assert g.read_vectors(path, 3) is None
    assert g.read_vectors(tmp_path / "missing.npy", 2) is None


def test_lexical_threshold_on_benchmark():
    scores = [(g.lexical(a, b), 1) for a, b in PAIRS["positives"]]
    scores += [(g.lexical(a, b), 0) for a, b in PAIRS["negatives"]]
    accuracy = np.mean([(s >= g.LEXICAL_MATCH) == bool(y) for s, y in scores])
    assert accuracy >= 0.95


@pytest.mark.smoke
def test_minilm_blend_separates_the_benchmark():
    pytest.importorskip("onnxruntime")
    from videoflow.engines.embed.onnx_st import OnnxTextEmbedder

    embedder = OnnxTextEmbedder(g.MODEL, "cpu")
    pairs = [(a, b, 1) for a, b in PAIRS["positives"]] + [(a, b, 0) for a, b in PAIRS["negatives"]]
    left = np.asarray(embedder.encode([a for a, _, _ in pairs]))
    right = np.asarray(embedder.encode([b for _, b, _ in pairs]))
    blend = 0.5 * (left * right).sum(axis=1) + 0.5 * np.array(
        [g.lexical(a, b) for a, b, _ in pairs]
    )
    labels = np.array([y for *_, y in pairs], dtype=bool)
    assert np.mean((blend >= g.SENTENCE_MATCH) == labels) >= 0.97


def words(lines):
    result, t = [], 0
    for line in lines:
        for token in line.split():
            result.append(Word(text=token, start_us=t, end_us=t + 300_000))
            t += 350_000
        t += 1_000_000
    return result


def test_import_stacks_a_retake_over_its_take(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from tests.editor.test_api import await_job, grant
    from videoflow.api.app import create_app
    from videoflow.editor.resolve import document_for
    from videoflow.project.models import new_project
    from videoflow.project.store import Bundle

    monkeypatch.setattr("videoflow.editor.imports.model_state", lambda _: "missing")
    sources = []
    for index, lines in enumerate((TAKE, OTHER, RETAKE)):
        source = tmp_path / "originals" / f"take{index}.wav"
        source.parent.mkdir(exist_ok=True)
        with wave.open(str(source), "wb") as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(16000)
            output.writeframes(
                (np.sin(np.arange(16000) * (0.1 + index)) * 1000).astype("<i2").tobytes()
            )
        source.with_suffix(".json").write_text(
            json.dumps(AnalysisFile(words=words(lines), summary="s").dump()), encoding="utf-8"
        )
        sources.append(source)
    bundle = Bundle.create(tmp_path / "edit.videoflow", new_project("Grouping"))
    app = create_app(bundle, token="t", desktop_secret="host-secret")
    with TestClient(app, base_url="http://127.0.0.1:8765") as client:
        client.get("/?token=t", follow_redirects=False)
        for source in sources:
            job = client.post(
                "/api/native-import", json={"handle": grant(client, source), "analyse": True}
            )
            assert await_job(client, job.json()["id"])["state"] == "done"
    names = {a.id: Path(a.path).name for a in bundle.project.assets}
    placed = {names[c.asset_id]: (c.start, c.layer) for c in document_for(bundle.project).clips}
    assert placed["take0.wav"][1] == 0 and placed["take1.wav"][1] == 0
    assert placed["take2.wav"] == (placed["take0.wav"][0], 1)
