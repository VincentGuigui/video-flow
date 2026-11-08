import importlib.util
import json
import shutil
import stat
import sys
import zipfile
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "release_artifacts", Path(__file__).resolve().parents[3] / "scripts/release_artifacts.py"
)
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


@pytest.fixture
def repo(tmp_path):
    files = {
        "backend/pyproject.toml": '[project]\nversion="1.2.3"\n',
        "backend/videoflow/__init__.py": '__version__ = "1.2.3"\n',
        "frontend/package.json": json.dumps({"version": "1.2.3"}),
        "frontend/package-lock.json": json.dumps(
            {"version": "1.2.3", "packages": {"": {"version": "1.2.3"}}}
        ),
        "docs/release_notes.md": "# Notes\n\n## 1.2.3 — today\n\nRelease content.\n",
        "releases/Video-Flow/Video-Flow.exe": "executable",
        "releases/Video-Flow/Video-Flow": "executable",
        "releases/Video-Flow/_internal/frontend/dist/index.html": "interface",
        "releases/Video-Flow/_internal/build-inputs.txt": "fingerprint",
    }
    for name, data in files.items():
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(data, encoding="utf-8")
    (tmp_path / "releases/Video-Flow/Video-Flow").chmod(0o755)
    return tmp_path


def test_version_mismatches_are_rejected(repo):
    assert release.version(repo) == "1.2.3"
    (repo / "frontend/package.json").write_text('{"version":"1.2.4"}')
    with pytest.raises(ValueError, match="disagree"):
        release.version(repo)


def test_zip_is_complete_and_checksum_is_verified(repo, monkeypatch):
    monkeypatch.setattr(release, "ROOT", repo)
    original = release.version
    monkeypatch.setattr(release, "version", lambda root=repo: original(root))
    (repo / "dist").mkdir()
    for platform in release.PLATFORMS:
        archive = release.archive(platform, repo)
        with zipfile.ZipFile(archive) as z:
            assert "Video-Flow/_internal/frontend/dist/index.html" in z.namelist()
            if platform == "linux-x64" and sys.platform != "win32":
                assert (z.getinfo("Video-Flow/Video-Flow").external_attr >> 16) & stat.S_IXUSR
        shutil.copy2(archive, repo / "dist" / archive.name)
        shutil.copy2(archive.with_suffix(".zip.sha256"), repo / "dist" / (archive.name + ".sha256"))
    release.verify()
    assert "Release content." in (repo / "notes.md").read_text(encoding="utf-8")
    path = next((repo / "dist").glob("*.zip"))
    path.write_bytes(b"damaged")
    with pytest.raises(ValueError, match="Checksum mismatch"):
        release.verify()


def test_incomplete_package_is_rejected(repo):
    (repo / "releases/Video-Flow/_internal/frontend/dist/index.html").unlink()
    with pytest.raises(ValueError, match="Incomplete"):
        release.archive("windows-x64", repo)
