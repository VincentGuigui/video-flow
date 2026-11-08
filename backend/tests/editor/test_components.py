import asyncio
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from videoflow.api.app import create_app
from videoflow.engines import components
from videoflow.hw import ai
from videoflow.preferences import Preferences
from videoflow.project.models import new_project
from videoflow.project.store import Bundle


def test_startup_detects_runtime_even_when_model_weights_are_present(monkeypatch):
    monkeypatch.setattr(
        components.importlib.util, "find_spec", lambda m: None if m == "torch" else True
    )
    monkeypatch.setattr(components, "cuda_status", lambda: None)
    state = components.Components(native=True).status(Preferences(summary_engine="qwen"))
    qwen = next(c for c in state["components"] if c["id"] == "qwen")
    assert not qwen["available"] and qwen["missing"] == ["torch"]
    assert all(
        c["id"] != "qwen"
        for c in components.Components(native=True).status(
            Preferences(summary_engine="deterministic")
        )["components"]
    )


def test_installer_whitelist_and_frozen_release(monkeypatch):
    monkeypatch.setattr(components, "uv_path", lambda: "uv")
    command = components.install_command("qwen")
    assert command[:5] == ["uv", "pip", "install", "--python", components.sys.executable]
    assert "torch==2.14.1" in command
    with pytest.raises(ValueError, match="Unknown"):
        components.install_command("arbitrary-package")
    whisper = components.install_command("whisper")
    assert "--no-deps" in whisper  # never replace a GPU/DML runtime with the CPU wheel
    monkeypatch.setattr(components.sys, "frozen", True, raising=False)
    with pytest.raises(ValueError, match="Reinstall"):
        components.install_command("qwen")


def test_component_install_rejected_in_browser_mode(tmp_path, monkeypatch):
    monkeypatch.setattr(components, "cuda_status", lambda: None)
    bundle = Bundle.create(tmp_path / "edit.video-flow", new_project("Test"))
    with TestClient(create_app(bundle, token="t"), base_url="http://127.0.0.1:8765") as client:
        assert client.get("/api/components").status_code == 401
        client.get("/?token=t", follow_redirects=False)
        assert client.get("/api/components").status_code == 200
        result = client.post("/api/components/qwen/install")
        assert result.status_code == 422
        assert "desktop app" in result.json()["detail"]


async def test_cancel_install_stops_owned_process(monkeypatch):
    entered = asyncio.Event()
    killed = []

    class Output:
        async def readline(self):
            entered.set()
            await asyncio.Future()

    process = SimpleNamespace(stdout=Output(), returncode=None)
    process.kill = lambda: killed.append(True)

    async def wait():
        process.returncode = -1
        return -1

    process.wait = wait

    async def spawn(*args, **kwargs):
        return process

    monkeypatch.setattr(components, "install_command", lambda c: ["uv"])
    monkeypatch.setattr(components.asyncio, "create_subprocess_exec", spawn)
    manager = components.Components(native=True)
    manager.start("qwen")
    await entered.wait()
    with pytest.raises(ValueError, match="already running"):
        manager.start("qwen")
    await manager.close()
    assert killed == [True]
    assert manager.job["state"] == "cancelled"


def test_cuda_startup_detects_silent_fallback(monkeypatch):
    ai.cuda_status.cache_clear()
    session = SimpleNamespace(get_providers=lambda: ["CPUExecutionProvider"])
    ort = SimpleNamespace(
        get_available_providers=lambda: ["CUDAExecutionProvider", "CPUExecutionProvider"],
        SessionOptions=lambda: SimpleNamespace(),
        InferenceSession=lambda *a, **kw: session,
    )
    monkeypatch.setattr(ai, "_import_ort", lambda: ort)
    monkeypatch.setattr(ai, "preload_cuda", lambda: None)
    result = ai.cuda_status()
    assert not result["available"]
    assert "fell back to CPU" in result["detail"]
    ai.cuda_status.cache_clear()


def test_cuda_probe_runs_inference_and_cpu_only_skips_it(monkeypatch):
    ai.cuda_status.cache_clear()
    ran = []
    session = SimpleNamespace(
        get_providers=lambda: ["CUDAExecutionProvider", "CPUExecutionProvider"],
        run=lambda *args: ran.append(args),
    )
    ort = SimpleNamespace(
        get_available_providers=lambda: ["CUDAExecutionProvider", "CPUExecutionProvider"],
        SessionOptions=lambda: SimpleNamespace(),
        InferenceSession=lambda *a, **kw: session,
    )
    monkeypatch.setattr(ai, "_import_ort", lambda: ort)
    monkeypatch.setattr(ai, "preload_cuda", lambda: None)
    assert ai.cuda_status()["available"] and ran
    monkeypatch.setattr(components, "cuda_status", lambda: pytest.fail("CPU must skip CUDA"))
    assert all(
        c["id"] != "cuda"
        for c in components.Components(native=True).status(Preferences(ai_device="cpu"))[
            "components"
        ]
    )
    ai.cuda_status.cache_clear()
