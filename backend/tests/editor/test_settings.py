import asyncio
import time
import wave

import pytest
from fastapi.testclient import TestClient

from videoflow import preferences, runtime
from videoflow.api.app import create_app
from videoflow.engines.downloads import ModelDownloads, model_state
from videoflow.engines.manifest import load_manifest
from videoflow.engines.summary import parse_summary
from videoflow.preferences import Preferences, required_models
from videoflow.project.models import new_project
from videoflow.project.store import Bundle


@pytest.fixture
def local_root(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime, "application_dir", lambda: tmp_path)
    monkeypatch.setattr(preferences, "application_dir", lambda: tmp_path)
    return tmp_path


def test_model_versions_missing_obsolete_and_up_to_date(local_root):
    key = "silero-vad"
    spec = load_manifest().get(key)
    snapshots = (
        runtime.model_directory() / "hf" / ("models--" + spec.repo.replace("/", "--")) / "snapshots"
    )
    assert model_state(key) == "missing"
    (snapshots / ("a" * 40)).mkdir(parents=True)
    assert model_state(key) == "obsolete"
    for name in spec.files:
        path = snapshots / spec.revision / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"synthetic model presence fixture")
    assert model_state(key) == "up-to-date"
    path.write_bytes(b"")
    assert model_state(key) == "obsolete"


def test_settings_persist_qwen_choice_without_downloading(local_root):
    bundle = Bundle.create(local_root / "edit.videoflow", new_project("Settings"))
    app = create_app(bundle, token="test")
    with TestClient(app, base_url="http://127.0.0.1:8765") as client:
        client.get("/?token=test", follow_redirects=False)
        payload = client.get("/api/settings").json()
        assert payload["directory"] == str(local_root / "models")
        assert all(m["state"] == "missing" for m in payload["models"])
        chosen = {**payload["preferences"], "summaryEngine": "qwen", "asrEngine": "faster-whisper"}
        response = client.put("/api/settings", json=chosen)
        assert response.status_code == 200, response.text
        qwen = next(m for m in response.json()["models"] if m["purpose"] == "summary")
        assert qwen["required"] and qwen["state"] == "missing"
        assert not (local_root / "models").exists()  # status/selection never downloads
        assert client.post("/api/models/unknown/download").status_code == 422
    assert preferences.load_preferences().summary_engine == "qwen"
    assert "faster-whisper-tiny" in required_models(preferences.load_preferences())


async def test_cancel_download_owns_worker_and_does_not_publish_model(local_root, monkeypatch):
    manager = ModelDownloads()
    entered = asyncio.Event()

    async def slow(*args, **kwargs):
        entered.set()
        await asyncio.Future()

    monkeypatch.setattr(manager.workers, "call", slow)
    manager.submit("silero-vad")
    await entered.wait()
    await manager.cancel("silero-vad")
    assert manager.jobs["silero-vad"]["state"] == "cancelled"
    assert model_state("silero-vad") == "missing"
    await manager.close()


def test_qwen_json_validation_and_keywords():
    assert parse_summary('```json\n{"summary":"A walk", "keywords":["Paris","Paris"]}\n```') == (
        "A walk",
        ["Paris"],
    )
    with pytest.raises(ValueError):
        parse_summary("Invented unstructured output")
    with pytest.raises(ValueError):
        parse_summary('{"summary":"A walk","keywords":"Paris"}')


def test_required_models_follow_engine_selection():
    selected = required_models(Preferences(asr_engine="faster-whisper", summary_engine="qwen"))
    assert selected == [
        "silero-vad",
        "faster-whisper-tiny",
        "paraphrase-multilingual-minilm-l12-v2",
        "qwen2.5-0.5b-instruct",
    ]


def test_import_waits_for_download_consent_and_can_be_cancelled(local_root):
    source = local_root / "source.wav"
    with wave.open(str(source), "wb") as output:
        output.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
        output.writeframes(b"\0\0" * 8000)
    bundle = Bundle.create(local_root / "edit.videoflow", new_project("Consent"))
    with TestClient(create_app(bundle, token="test"), base_url="http://127.0.0.1:8765") as client:
        client.get("/?token=test", follow_redirects=False)
        response = client.post("/api/import-path", json={"path": str(source), "analyse": True})
        identifier = response.json()["id"]
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            job = client.get("/api/jobs").json()[0]
            if job["state"] == "waiting-models":
                break
            time.sleep(0.05)
        assert job["state"] == "waiting-models", job
        assert job["modelsNeeded"]
        assert not (local_root / "models").exists()
        assert client.post(f"/api/jobs/cancel?job_id={identifier}").status_code == 200
        assert client.get("/api/jobs").json()[0]["state"] == "cancelled"


def test_models_unused_by_the_editor_are_hidden_and_not_downloadable():
    downloads = ModelDownloads()
    listed = {m["id"] for m in downloads.status(Preferences())["models"]}
    hidden = {k for k, s in load_manifest().models.items() if not s.in_editor}
    assert hidden == {"dinov2-small"}
    assert not listed & hidden
    assert {
        "silero-vad",
        "parakeet-tdt-0.6b-v3-int8",
        "paraphrase-multilingual-minilm-l12-v2",
    } <= listed
    with pytest.raises(ValueError, match="not used by the editor"):
        downloads.submit("dinov2-small")
