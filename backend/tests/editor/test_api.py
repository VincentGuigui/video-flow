import hashlib
import json
import time
import wave
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

from videoflow.api.app import create_app
from videoflow.editor.analysis import AnalysisFile, cached_path, load_analysis, store_analysis
from videoflow.editor.resolve import document_for
from videoflow.project.library import ProjectLibrary
from videoflow.project.models import new_project
from videoflow.project.store import Bundle


@pytest.fixture
def original(tmp_path):
    source = tmp_path / "originals" / "café take 01.wav"
    source.parent.mkdir()
    with wave.open(str(source), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(16000)
        output.writeframes((np.sin(np.arange(16000) * 0.1) * 1000).astype("<i2").tobytes())
    return source


@pytest.fixture
def app_bundle(tmp_path):
    bundle = Bundle.create(tmp_path / "project" / "edit.videoflow", new_project("Test"))
    app = create_app(
        bundle,
        token="test-token",
        desktop_secret="host-secret",
        media_roots=[tmp_path / "browser-root"],
        library=ProjectLibrary(tmp_path / "recent-projects.json"),
    )
    return app, bundle


@pytest.fixture
def client(app_bundle):
    app, _ = app_bundle
    with TestClient(app, base_url="http://127.0.0.1:8765") as client:
        client.get("/?token=test-token", follow_redirects=False)
        yield client


def grant(client, source, asset_id=None):
    response = client.post(
        "/api/desktop/selection",
        headers={"X-VideoFlow-Desktop": "host-secret"},
        json={"paths": [str(source)], "assetId": asset_id},
    )
    assert response.status_code == 200, response.text
    return response.json()["selections"][0]["handle"]


def await_job(client, job_id):
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        job = next(j for j in client.get("/api/jobs").json() if j["id"] == job_id)
        if job["state"] in ("done", "failed", "cancelled"):
            return job
        time.sleep(0.03)
    raise AssertionError("Import did not finish")


def test_save_copy_home_and_scoped_projects(client, app_bundle, tmp_path):
    _, original = app_bundle
    identifier = original.project.id
    response = client.post("/api/project/save", json={"baseRevision": 0, "name": "First"})
    assert response.status_code == 200, response.text
    assert client.get("/api/project").json()["project"]["name"] == "First"
    assert (tmp_path / "project" / "First.video-flow" / "project.json").is_file()
    revision = client.get("/api/project").json()["project"]["revision"]
    assert client.post("/api/project/save", json={"baseRevision": 0}).status_code == 409
    response = client.post(
        "/api/project/save", json={"baseRevision": revision, "name": "Second", "copy": True}
    )
    assert response.status_code == 200, response.text
    second = client.get("/api/project").json()
    assert second["project"]["id"] != identifier and second["open"]
    assert (tmp_path / "project" / "Second.video-flow").is_dir()  # beside the original
    assert [e["name"] for e in client.get("/api/projects").json()] == ["Second", "First"]
    opened = client.post("/api/projects/action", json={"kind": "open", "id": identifier})
    assert opened.status_code == 200
    assert client.get("/api/project").json()["project"]["name"] == "First"
    removed = client.post(
        "/api/projects/action", json={"kind": "remove", "id": second["project"]["id"]}
    )
    assert removed.status_code == 200
    assert [e["name"] for e in client.get("/api/projects").json()] == ["First"]
    assert (tmp_path / "project" / "Second.video-flow").is_dir()  # files untouched
    bad = client.post("/api/projects/action", json={"kind": "open", "id": "../other"})
    assert bad.status_code == 422


def test_new_and_open_projects_through_native_folder_selections(client, tmp_path):
    work = tmp_path / "Holiday"
    work.mkdir()

    def folder(path, purpose):
        response = client.post(
            "/api/desktop/folder",
            headers={"X-VideoFlow-Desktop": "host-secret"},
            json={"path": str(path), "purpose": purpose},
        )
        assert response.status_code == 200, response.text
        return response.json()["handle"]

    assert (
        client.post(
            "/api/desktop/folder", json={"path": str(work), "purpose": "workdir"}
        ).status_code
        == 403
    )  # the renderer cannot name folders
    handle = folder(work, "workdir")
    created = client.post(
        "/api/projects/action", json={"kind": "new", "name": "Day 1", "folder": handle}
    )
    assert created.status_code == 200, created.text
    assert (work / "Day 1.video-flow" / "project.json").is_file()
    reused = client.post(
        "/api/projects/action", json={"kind": "new", "name": "Day 2", "folder": handle}
    )
    assert reused.status_code == 422  # handles are single use
    assert (
        client.post(
            "/api/desktop/folder",
            headers={"X-VideoFlow-Desktop": "host-secret"},
            json={"path": str(work), "purpose": "project"},
        ).status_code
        == 422
    )  # not a project folder
    client.post("/api/projects/action", json={"kind": "close"})
    assert not client.get("/api/project").json()["open"]
    opened = client.post(
        "/api/projects/action",
        json={"kind": "open", "folder": folder(work / "Day 1.video-flow", "project")},
    )
    assert opened.status_code == 200, opened.text
    project = client.get("/api/project").json()
    assert project["open"] and project["project"]["name"] == "Day 1"


def test_render_api_progress_download_and_native_save(client, original, tmp_path):
    job = client.post(
        "/api/native-import", json={"handle": grant(client, original), "analyse": False}
    ).json()
    assert await_job(client, job["id"])["state"] == "done"
    revision = client.get("/api/project").json()["project"]["revision"]
    assert client.post("/api/render", json={"baseRevision": 0}).status_code == 409
    job = client.post(
        "/api/render", json={"baseRevision": revision, "preset": "draft", "normalize": False}
    ).json()
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        state = client.get("/api/renders").json()[-1]
        if state["state"] in ("done", "failed"):
            break
        time.sleep(0.05)
    assert state["state"] == "done", state
    assert client.get(f"/api/renders/{job['id']}/file").headers["content-type"] == "video/mp4"
    target = tmp_path / "saved.mp4"
    payload = {"id": job["id"], "path": str(target)}
    assert client.post("/api/desktop/render-save", json=payload).status_code == 403
    headers = {"X-VideoFlow-Desktop": "host-secret"}
    assert client.post("/api/desktop/render-save", json=payload, headers=headers).status_code == 200
    assert target.is_file()
    payload["path"] = str(original)
    assert client.post("/api/desktop/render-save", json=payload, headers=headers).status_code == 422


def test_auth_host_origin_and_cookie_flow(app_bundle):
    app, _ = app_bundle
    with TestClient(app, base_url="http://127.0.0.1:8765") as client:
        assert client.get("/api/project").status_code == 401
        assert client.get("/api/project", headers={"Host": "evil.local"}).status_code == 403
        response = client.get("/?token=test-token", follow_redirects=False)
        assert response.status_code == 303
        assert "HttpOnly" in response.headers["set-cookie"]
        assert "SameSite=strict" in response.headers["set-cookie"]
        assert response.headers["location"] == "/"
        assert client.get("/api/project").status_code == 200
        assert (
            client.post("/api/jobs/cancel", headers={"Origin": "http://evil.local"}).status_code
            == 403
        )


def test_native_path_import_no_copies_unicode_and_replay_protection(client, app_bundle, original):
    _, bundle = app_bundle
    before = hashlib.sha256(original.read_bytes()).hexdigest()
    assert (
        client.post("/api/import-path", json={"path": str(original), "analyse": False}).status_code
        == 403
    )
    assert client.post("/api/desktop/selection", json={"paths": [str(original)]}).status_code == 403
    handle = grant(client, original)
    response = client.post(
        "/api/native-import", json={"handle": handle, "analyse": False, "path": "C:/not-granted"}
    )
    assert response.status_code == 200
    job = await_job(client, response.json()["id"])
    assert job["state"] == "done", job
    assert (
        client.post("/api/native-import", json={"handle": handle, "analyse": False}).status_code
        == 403
    )
    asset = bundle.project.assets[0]
    assert Path(asset.path) == original.resolve()
    assert not (bundle.path / "media").exists()
    assert before == hashlib.sha256(original.read_bytes()).hexdigest()
    assert document_for(bundle.project).clips[0].kind == "audio"
    media = client.get(f"/api/media/{asset.id}", headers={"Range": "bytes=0-31"})
    assert media.status_code == 206 and media.content == original.read_bytes()[:32]
    assert Bundle(bundle.path).load().assets[0].path == str(original.resolve())


def test_renderer_cannot_create_arbitrary_source_or_upload(client, original):
    asset = {
        "id": "malicious",
        "path": str(original),
        "contentHash": "fake",
        "probe": {"durationUs": 1000000, "audioStreams": []},
    }
    response = client.patch(
        "/api/project", json={"baseRevision": 0, "commands": [{"type": "AddAsset", "asset": asset}]}
    )
    assert response.status_code == 403
    assert (
        client.post("/api/uploads/batch/secret.wav", content=original.read_bytes()).status_code
        == 403
    )
    assert client.get("/api/media/malicious").status_code == 404


def test_revision_conflict_and_command_inverse(client):
    commands = [{"type": "SetEditor", "document": {"version": 1, "clips": []}}]
    response = client.patch("/api/project", json={"baseRevision": 0, "commands": commands})
    assert response.status_code == 200
    assert response.json()["project"]["revision"] == 1
    assert (
        client.patch("/api/project", json={"baseRevision": 0, "commands": commands}).status_code
        == 409
    )
    inverse = response.json()["inverses"]
    response = client.patch("/api/project", json={"baseRevision": 1, "commands": inverse})
    assert "editor" not in response.json()["project"]


def test_cached_analysis_reused_and_readonly_fallback(client, app_bundle, original, monkeypatch):
    from videoflow.media.hashing import content_hash_sync

    _, bundle = app_bundle
    digest = content_hash_sync(original)
    analysis = AnalysisFile(source_hash=digest, words=[], summary="Cached", keywords=["test"])
    monkeypatch.setattr(
        "videoflow.editor.analysis.write_sidecar",
        lambda *_: (_ for _ in ()).throw(PermissionError("read-only")),
    )
    location, warning = store_analysis(original, analysis, bundle)
    assert warning and location == cached_path(bundle, digest)
    assert not original.with_suffix(".json").exists()
    assert load_analysis(original, digest, bundle) == analysis
    handle = grant(client, original)
    response = client.post("/api/native-import", json={"handle": handle, "analyse": True})
    job = await_job(client, response.json()["id"])
    assert job["state"] == "done" and job["cached"]


def test_unrelated_sidecar_is_preserved_instead_of_overwritten(app_bundle, original):
    _, bundle = app_bundle
    sidecar = original.with_suffix(".json")
    sidecar.write_text('{"camera":"notes"}', encoding="utf-8")
    analysis = AnalysisFile(source_hash="digest", words=[], summary="Test")
    location, warning = store_analysis(original, analysis, bundle)
    assert warning and location == cached_path(bundle, "digest")
    assert json.loads(sidecar.read_bytes()) == {"camera": "notes"}
    assert load_analysis(original, "digest", bundle) == analysis


def test_reimport_known_source_can_add_analysis_without_duplicate_clips(
    client, app_bundle, original
):
    from videoflow.media.hashing import content_hash_sync

    first = client.post(
        "/api/native-import", json={"handle": grant(client, original), "analyse": False}
    )
    assert await_job(client, first.json()["id"])["state"] == "done"
    _, bundle = app_bundle
    analysis = AnalysisFile(source_hash=content_hash_sync(original), summary="Reused", words=[])
    original.with_suffix(".json").write_text(json.dumps(analysis.dump()), encoding="utf-8")
    second = client.post(
        "/api/native-import", json={"handle": grant(client, original), "analyse": True}
    )
    job = await_job(client, second.json()["id"])
    assert job["state"] == "done" and job["cached"]
    assert len(bundle.project.assets) == 1
    assert len(document_for(bundle.project).clips) == 1


def test_missing_source_offline_and_scoped_relink_retains_edit(
    client, app_bundle, original, tmp_path
):
    _, bundle = app_bundle
    job = client.post(
        "/api/native-import", json={"handle": grant(client, original), "analyse": False}
    ).json()
    assert await_job(client, job["id"])["state"] == "done"
    asset = bundle.project.assets[0]
    before = document_for(bundle.project).dump()
    moved = tmp_path / "renamed.wav"
    original.rename(moved)
    assert asset.id in client.get("/api/project").json()["offline"]
    handle = grant(client, moved, asset.id)
    assert client.post("/api/native-import", json={"handle": handle}).status_code == 403
    result = client.post("/api/native-relink", json={"handle": handle, "assetId": asset.id})
    assert result.status_code == 200, result.text
    assert bundle.project.assets[0].path == str(moved.resolve())
    assert document_for(bundle.project).dump() == before
    assert client.get("/api/project").json()["offline"] == []


def test_global_cancel_stops_current_and_queued_imports(client, app_bundle, original, monkeypatch):
    import asyncio

    async def slow(*args, **kwargs):
        await asyncio.sleep(60)

    monkeypatch.setattr("videoflow.editor.imports.ingest_files", slow)
    ids = []
    for _ in range(2):
        ids.append(
            client.post(
                "/api/native-import", json={"handle": grant(client, original), "analyse": False}
            ).json()["id"]
        )
    assert client.post("/api/jobs/cancel").status_code == 200
    jobs = client.get("/api/jobs").json()
    assert all(job["state"] == "cancelled" for job in jobs if job["id"] in ids)
    assert not app_bundle[1].project.assets


def test_title_picture_is_drawn_at_the_project_size(client):
    import json
    from io import BytesIO

    from PIL import Image

    spec = json.dumps({"text": "Hello", "style": "lower_third", "box": True})
    response = client.get("/api/title", params={"spec": spec})
    assert response.status_code == 200 and response.headers["content-type"] == "image/png"
    picture = Image.open(BytesIO(response.content))
    assert picture.size == (1920, 1080) and picture.mode == "RGBA"
    assert client.get("/api/title", params={"spec": '{"text": " "}'}).status_code == 422
    assert client.get("/api/title", params={"spec": "nope"}).status_code == 422


def test_cache_lists_sizes_opens_root_and_clears(client, app_bundle, monkeypatch):
    from videoflow.api import app as module

    opened = []
    monkeypatch.setattr(module, "open_folder", opened.append)
    _, bundle = app_bundle
    (bundle.proxies_dir / "p.mp4").write_bytes(b"x" * 1000)
    usage = client.get("/api/cache").json()
    mine = next(p for p in usage["projects"] if p["current"])
    assert mine["id"] == bundle.project.id and mine["name"] == "Test"
    assert mine["size"] >= 1000 and usage["size"] >= mine["size"]
    assert bundle.cache_dir.parent == Path(usage["root"])
    assert client.post("/api/cache/open").json() == {"path": usage["root"]}
    assert opened == [Path(usage["root"])]
    assert client.post("/api/cache/clear").json() == {"failed": []}
    assert not (bundle.proxies_dir / "p.mp4").exists() and bundle.proxies_dir.is_dir()
    after = client.get("/api/cache").json()
    assert next(p for p in after["projects"] if p["current"])["size"] < 1000


def test_close_and_rename_release_and_move_the_open_project(client, app_bundle, tmp_path):
    _, original = app_bundle
    identifier = original.project.id
    revision = client.get("/api/project").json()["project"]["revision"]
    response = client.post("/api/project/save", json={"baseRevision": revision, "name": "Cut A"})
    assert response.status_code == 200, response.text
    assert [Path(e["path"]).name for e in client.get("/api/projects").json()] == [
        "Cut A.video-flow"
    ]
    closed = client.post("/api/projects/action", json={"kind": "close"})
    assert closed.status_code == 200, closed.text
    renamed = client.post(
        "/api/projects/action", json={"kind": "rename", "id": identifier, "name": "Cut B"}
    )
    assert renamed.status_code == 200, renamed.text
    entry = client.get("/api/projects").json()[0]
    assert entry["name"] == "Cut B" and Path(entry["path"]).name == "Cut B.video-flow"
    opened = client.post("/api/projects/action", json={"kind": "open", "id": identifier})
    assert opened.status_code == 200
    assert client.get("/api/project").json()["project"]["name"] == "Cut B"
