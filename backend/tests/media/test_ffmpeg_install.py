import hashlib
import io
import tarfile
import threading
import zipfile
from dataclasses import replace
from pathlib import Path

import pytest

from videoflow.media import ffmpeg_install
from videoflow.media.ffmpeg_install import BUILDS, install

ROOT = Path(__file__).resolve().parents[3]


def archive(tmp_path: Path, kind: str) -> Path:
    if kind == "zip":
        path = tmp_path / "build.zip"
        with zipfile.ZipFile(path, "w") as bundle:
            for name in ("ffmpeg.exe", "ffprobe.exe", "ffplay.exe"):
                bundle.writestr(f"ffmpeg-7.1.1-full_build/bin/{name}", b"exe")
            bundle.writestr("ffmpeg-7.1.1-full_build/LICENSE", b"GPL")
            bundle.writestr("ffmpeg-7.1.1-full_build/README.txt", b"readme")
        return path
    path = tmp_path / "build.tar.xz"
    with tarfile.open(path, "w:xz") as bundle:
        for name, data in (("ffmpeg", b"elf"), ("ffprobe", b"elf"), ("GPLv3.txt", b"GPL")):
            info = tarfile.TarInfo(f"ffmpeg-7.0.2-amd64-static/{name}")
            info.size = len(data)
            bundle.addfile(info, io.BytesIO(data))
    return path


@pytest.mark.parametrize("key,kind", [("windows-x64", "zip"), ("linux-x64", "tar.xz")])
def test_install_verifies_and_unpacks_binaries_and_licences(tmp_path, key, kind):
    source = archive(tmp_path, kind)
    data = source.read_bytes()
    build = replace(
        BUILDS[key],
        url=source.as_uri(),
        sha256=hashlib.sha256(data).hexdigest(),
        size=len(data),
    )
    target = tmp_path / "tools" / "ffmpeg"
    steps = []
    install(build, target, lambda p, m: steps.append(p), threading.Event())
    exe = ".exe" if kind == "zip" else ""
    names = sorted(p.name for p in target.iterdir())
    assert f"ffmpeg{exe}" in names and f"ffprobe{exe}" in names
    assert any(n in names for n in ("LICENSE", "GPLv3.txt"))
    assert "ffplay.exe" not in names and steps[-1] == 1.0


def test_checksum_mismatch_installs_nothing(tmp_path):
    source = archive(tmp_path, "zip")
    build = replace(BUILDS["windows-x64"], url=source.as_uri(), sha256="0" * 64, size=1)
    target = tmp_path / "tools" / "ffmpeg"
    with pytest.raises(ValueError, match="checksum"):
        install(build, target, lambda p, m: None, threading.Event())
    assert not target.exists()


def test_install_scripts_pin_the_same_builds():
    sh = (ROOT / "scripts" / "install.sh").read_text()
    ps1 = (ROOT / "scripts" / "install.ps1").read_text()
    assert BUILDS["linux-x64"].url in sh and BUILDS["linux-x64"].sha256 in sh
    assert BUILDS["windows-x64"].url in ps1 and BUILDS["windows-x64"].sha256 in ps1


def test_only_x64_windows_and_linux_have_a_pinned_build(monkeypatch):
    monkeypatch.setattr(ffmpeg_install.platform, "machine", lambda: "arm64")
    assert ffmpeg_install.current_build() is None
