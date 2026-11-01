"""Download FFmpeg on the user's request into tools/ffmpeg/ beside the application.

FFmpeg is a separate program: Video-Flow runs its executables and never links to it or
modifies it. The archives come unchanged from their distributors, pinned by URL and
SHA-256; their licence files are kept next to the binaries. The install scripts pin the
same builds (tests check that they agree).
"""

import hashlib
import platform
import shutil
import sys
import tarfile
import tempfile
import threading
import urllib.request
import zipfile
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from videoflow.runtime import application_dir


@dataclass(frozen=True)
class FfmpegBuild:
    platform: str
    version: str
    url: str
    sha256: str
    size: int
    license: str
    distributor: str
    """Who builds and distributes the archive (and provides its source)."""
    notices: tuple[str, ...]
    """Licence and readme files kept next to the binaries."""


BUILDS = {
    "windows-x64": FfmpegBuild(
        platform="windows-x64",
        version="7.1.1",
        url="https://github.com/GyanD/codexffmpeg/releases/download/7.1.1/ffmpeg-7.1.1-full_build.zip",
        sha256="d760e1b3574402ed18b4865851f87d87e73965a982e6453212df8621fed1c508",
        size=177650503,
        license="GPL-3.0",
        distributor="gyan.dev (https://www.gyan.dev/ffmpeg/builds/)",
        notices=("LICENSE", "README.txt"),
    ),
    "linux-x64": FfmpegBuild(
        platform="linux-x64",
        version="7.0.2",
        url="https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz",
        sha256="abda8d77ce8309141f83ab8edf0596834087c52467f6badf376a6a2a4c87cf67",
        size=41888096,
        license="GPL-3.0",
        distributor="John Van Sickle (https://johnvansickle.com/ffmpeg/)",
        notices=("GPLv3.txt", "readme.txt"),
    ),
}

Progress = Callable[[float, str], None]


def platform_key() -> str | None:
    machine = platform.machine().casefold()
    if machine not in ("amd64", "x86_64"):
        return None
    if sys.platform == "win32":
        return "windows-x64"
    if sys.platform.startswith("linux"):
        return "linux-x64"
    return None


def current_build() -> FfmpegBuild | None:
    """The pinned build for this machine, or None (install FFmpeg manually)."""
    key = platform_key()
    return BUILDS.get(key) if key else None


def tools_dir() -> Path:
    return application_dir() / "tools" / "ffmpeg"


def describe(build: FfmpegBuild) -> dict[str, Any]:
    return asdict(build)


def install(build: FfmpegBuild, target: Path, progress: Progress, cancel: threading.Event) -> None:
    """Download, verify (SHA-256) and unpack ffmpeg and ffprobe with their licence files."""
    exe = ".exe" if build.platform.startswith("windows") else ""
    with tempfile.TemporaryDirectory(prefix="videoflow-ffmpeg-") as folder:
        archive = Path(folder) / ("ffmpeg.zip" if build.url.endswith(".zip") else "ffmpeg.tar.xz")
        digest = hashlib.sha256()
        done = 0
        with urllib.request.urlopen(build.url, timeout=60) as response, archive.open("wb") as out:
            while chunk := response.read(1 << 20):
                if cancel.is_set():
                    raise InterruptedError("FFmpeg download cancelled")
                out.write(chunk)
                digest.update(chunk)
                done += len(chunk)
                progress(min(0.95, done / build.size * 0.95), "Downloading FFmpeg")
        if digest.hexdigest() != build.sha256:
            raise ValueError(
                "The downloaded FFmpeg does not match its pinned checksum "
                "(the distributor may have published a new build); nothing was installed"
            )
        progress(0.96, "Unpacking FFmpeg")
        unpacked = Path(folder) / "x"
        if archive.suffix == ".zip":
            with zipfile.ZipFile(archive) as bundle:
                bundle.extractall(unpacked)
        else:
            with tarfile.open(archive) as bundle:
                bundle.extractall(unpacked, filter="data")
        wanted = {f"ffmpeg{exe}", f"ffprobe{exe}", *build.notices}
        found = {p.name: p for p in unpacked.rglob("*") if p.is_file() and p.name in wanted}
        if f"ffmpeg{exe}" not in found or f"ffprobe{exe}" not in found:
            raise ValueError("ffmpeg or ffprobe is missing from the downloaded archive")
        target.mkdir(parents=True, exist_ok=True)
        for name, path in found.items():
            shutil.copy2(path, target / name)
            if name.startswith(("ffmpeg", "ffprobe")):
                (target / name).chmod(0o755)
        progress(1.0, "FFmpeg installed")
