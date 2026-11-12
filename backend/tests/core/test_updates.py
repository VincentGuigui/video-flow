"""Updates from the GitHub releases (docs/features/getting-started/updates.md)."""

import hashlib
import json
import subprocess
import sys
import threading
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from videoflow import preferences, runtime, updates
from videoflow.api.app import create_app
from videoflow.project.models import new_project
from videoflow.project.store import Bundle

PLATFORM = "linux-x64"
BODY = """# How to install

* Extract the complete Video-Flow zip to a folder before running.


# What's new ?

* Search what is said.
* Faster previews.
"""


def _api(version: str = "0.40.0", **assets: str) -> dict:
    return {
        "tag_name": f"v{version}",
        "html_url": f"https://github.com/x/y/releases/tag/v{version}",
        "body": BODY,
        "draft": False,
        "prerelease": False,
        "assets": [
            {"name": name, "browser_download_url": url, "size": 10} for name, url in assets.items()
        ],
    }


def test_versions_and_release_notes():
    assert updates.is_newer("0.40.0", "0.36.0") and updates.is_newer("1.0.0", "0.99.9")
    assert not updates.is_newer("0.36.0", "0.36.0") and not updates.is_newer("0.9.0", "0.36.0")
    assert not updates.is_newer("latest", "0.36.0")
    assert updates.whats_new(BODY) == ["Search what is said.", "Faster previews."]


def test_release_assets_of_this_platform():
    zip_name = f"Video-Flow-0.40.0-{PLATFORM}.zip"
    data = _api(**{zip_name: "https://z", zip_name + ".sha256": "https://s"})
    release = updates.parse_release(data, PLATFORM)
    assert release is not None and release.version == "0.40.0"
    assert release.archive == "https://z" and release.checksum == "https://s"
    assert release.notes == ["Search what is said.", "Faster previews."]
    other = updates.parse_release(data, "windows-x64")
    assert other is not None and other.archive is None  # offered, not installable
    assert updates.parse_release({**data, "prerelease": True}, PLATFORM) is None
    assert updates.parse_release({**data, "tag_name": "nightly"}, PLATFORM) is None


def test_check_from_source_is_not_installable():
    release = updates.Release("9.0.0", "https://page", archive="https://z", checksum="https://s")
    result = updates.check(release, current="0.36.0")
    assert result["newer"] and not result["installable"]
    assert "source" in result["reason"]
    assert not updates.check(release, current="9.0.0")["newer"]


def _release_zip(folder: Path, version: str = "0.40.0") -> tuple[updates.Release, Path]:
    """A release ZIP like the release workflow's, served from file: URLs."""
    archive = folder / f"Video-Flow-{version}-{PLATFORM}.zip"
    exe = updates.executable_name(PLATFORM)
    with zipfile.ZipFile(archive, "w") as bundle:
        info = zipfile.ZipInfo(f"Video-Flow/{exe}")
        info.external_attr = 0o755 << 16
        bundle.writestr(info, "new executable")
        bundle.writestr("Video-Flow/_internal/lib.txt", version)
        bundle.writestr("Video-Flow/add-video-flow-to-menu.sh", "menu")
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    checksum = archive.with_suffix(".zip.sha256")
    checksum.write_text(f"{digest}  {archive.name}\n")
    release = updates.Release(
        version, "page", archive=archive.as_uri(), checksum=checksum.as_uri(), size=0
    )
    return release, archive


def test_download_verifies_and_unpacks(tmp_path):
    release, _ = _release_zip(tmp_path)
    steps: list[str] = []
    app = updates.download(
        release, tmp_path / "updates" / "0.40.0", lambda v, p: steps.append(p), threading.Event()
    )
    exe = app / updates.executable_name()
    assert exe.read_text() == "new executable" and (app / "_internal" / "lib.txt").is_file()
    if sys.platform != "win32":
        assert exe.stat().st_mode & 0o111  # executable bit kept
    assert steps[-1] == "Update ready" and not (app.parent.parent / "release.zip").exists()


def test_download_rejects_a_wrong_checksum(tmp_path):
    release, _ = _release_zip(tmp_path)
    Path(release.checksum.removeprefix("file://")).write_text("0" * 64)
    with pytest.raises(ValueError, match="checksum"):
        updates.download(release, tmp_path / "u", lambda v, p: None, threading.Event())
    assert not (tmp_path / "u" / "files").exists()


def test_download_can_be_cancelled(tmp_path):
    release, _ = _release_zip(tmp_path)
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(InterruptedError):
        updates.download(release, tmp_path / "u", lambda v, p: None, cancel)


def _install(folder: Path, version: str) -> None:
    (folder / "_internal").mkdir(parents=True)
    (folder / "_internal" / "lib.txt").write_text(version)
    (folder / updates.executable_name()).write_text(f"executable {version}")


def test_apply_replaces_app_files_and_keeps_the_rest(tmp_path):
    target, source = tmp_path / "app", tmp_path / "new"
    _install(target, "0.36.0")
    (target / "_internal" / "old-only.txt").write_text("gone after update")
    for kept in ("models", "tools", "cache"):
        (target / kept).mkdir()
        (target / kept / "data").write_text(kept)
    (target / "settings.json").write_text("{}")
    _install(source, "0.40.0")
    started: list[Path] = []
    old = subprocess.Popen([sys.executable, "-c", "pass"])  # the closed old version
    old.wait()
    updates.apply(source, target, old.pid, relaunch=started.append)
    assert (target / "_internal" / "lib.txt").read_text() == "0.40.0"
    assert not (target / "_internal" / "old-only.txt").exists()
    assert (target / updates.executable_name()).read_text() == "executable 0.40.0"
    assert all((target / k / "data").read_text() == k for k in ("models", "tools", "cache"))
    assert (target / "settings.json").is_file()
    assert started == [target / updates.executable_name()]
    backup = next((target / updates.UPDATES).glob("previous-*"))
    assert (backup / "_internal" / "lib.txt").read_text() == "0.36.0"


def test_failed_apply_puts_the_old_files_back(tmp_path, monkeypatch):
    target, source = tmp_path / "app", tmp_path / "new"
    _install(target, "0.36.0")
    _install(source, "0.40.0")
    real = updates.shutil.copytree

    def broken(*args, **kwargs):
        real(*args, **kwargs)
        raise OSError("disk full")

    monkeypatch.setattr(updates.shutil, "copytree", broken)
    with pytest.raises(OSError, match="disk full"):
        updates.replace_files(source, target)
    assert (target / "_internal" / "lib.txt").read_text() == "0.36.0"
    assert (target / updates.executable_name()).read_text() == "executable 0.36.0"


def test_api_checks_skips_and_refuses_to_install_from_source(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime, "application_dir", lambda: tmp_path)
    monkeypatch.setattr(preferences, "application_dir", lambda: tmp_path)
    calls: list[int] = []

    def latest():
        calls.append(1)
        return updates.Release("9.0.0", "https://page", notes=["New"])

    monkeypatch.setattr(updates, "fetch_latest", latest)
    bundle = Bundle.create(tmp_path / "edit.video-flow", new_project("Updates"))
    with TestClient(create_app(bundle, token="t"), base_url="http://127.0.0.1:8765") as client:
        client.get("/?token=t", follow_redirects=False)
        state = client.get("/api/update", params={"start": True}).json()
        assert state["newer"] and state["release"]["notes"] == ["New"]
        assert not state["installable"] and state["enabled"] and not state["skipped"]
        client.get("/api/update")
        assert len(calls) == 1  # checked once per run unless refreshed
        assert client.post("/api/update/install").status_code == 409
        assert client.post("/api/update/restart").status_code == 409
        assert client.post("/api/update/skip").json()["skipped"]
        assert preferences.load_preferences().skipped_update == "9.0.0"
        settings = client.get("/api/settings").json()["preferences"]
        client.put("/api/settings", json={**settings, "checkUpdates": False})
        assert not client.get("/api/update", params={"start": True}).json()["enabled"]
    assert json.loads((tmp_path / "settings.json").read_text())["checkUpdates"] is False


def test_api_survives_being_offline(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime, "application_dir", lambda: tmp_path)
    monkeypatch.setattr(preferences, "application_dir", lambda: tmp_path)

    def offline():
        raise OSError("no network")

    monkeypatch.setattr(updates, "fetch_latest", offline)
    bundle = Bundle.create(tmp_path / "edit.video-flow", new_project("Offline"))
    with TestClient(create_app(bundle, token="t"), base_url="http://127.0.0.1:8765") as client:
        client.get("/?token=t", follow_redirects=False)
        state = client.get("/api/update", params={"start": True})
        assert state.status_code == 200 and not state.json()["newer"]
        assert client.get("/api/update", params={"refresh": True}).status_code == 502


def test_cleanup_removes_applied_updates(tmp_path):
    (tmp_path / updates.UPDATES / "previous-1" / "_internal").mkdir(parents=True)
    updates.cleanup(tmp_path)
    assert not (tmp_path / updates.UPDATES).exists()
