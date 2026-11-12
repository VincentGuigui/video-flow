"""Updates from the GitHub releases (docs/features/getting-started/updates.md).

1. **Check**: at start, the latest published release of the repository is read from the
   GitHub API (`releases/latest`: no drafts, no pre-releases). It is newer when its tag
   `v<version>` is above the running version.
2. **Download**, on the user's request: the ZIP of this platform
   (`Video-Flow-<version>-<platform>.zip`) and its `.sha256` file; the ZIP must match the
   checksum. It is unpacked into `updates/<version>/` beside the application.
3. **Apply**: the running app starts the new version's executable with
   `apply-update --target <application folder> --pid <its process id>` and closes. That
   process waits for the old one to end, moves the old application files (the executable,
   `_internal/` and the shortcut script) into `updates/previous-<time>/`, copies its own
   in their place and starts the updated app. Everything else beside the executable stays:
   models, tools, cache, settings and logs. On failure the old files are put back.
4. The next start deletes `updates/`.

`apply-update` is a contract between versions: the running version calls the command of
the downloaded one, so its options must not change.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
import zipfile
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from videoflow import __version__
from videoflow.media.ffmpeg_install import platform_key
from videoflow.runtime import application_dir

REPOSITORY = "VincentGuigui/video-flow"
LATEST_URL = f"https://api.github.com/repos/{REPOSITORY}/releases/latest"
NAME = "Video-Flow"
UPDATES = "updates"
CHECK_TIMEOUT_S = 6
WAIT_EXIT_S = 120
Progress = Callable[[float, str], None]
log = logging.getLogger(__name__)


def executable_name(platform: str | None = None) -> str:
    platform = platform or platform_key() or ""
    return NAME + (".exe" if platform.startswith("windows") or sys.platform == "win32" else "")


def parse_version(text: str) -> tuple[int, ...] | None:
    match = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", text.strip())
    return tuple(int(part) for part in match.groups()) if match else None


def is_newer(candidate: str, current: str) -> bool:
    new, old = parse_version(candidate), parse_version(current)
    return new is not None and old is not None and new > old


def whats_new(body: str) -> list[str]:
    """The `* ` lines of the release text after its "What's new" heading."""
    lines = body.splitlines()
    start = next(
        (i for i, line in enumerate(lines) if line.lstrip("# ").lower().startswith("what")),
        None,
    )
    if start is None:
        return []
    return [line[2:].strip() for line in lines[start + 1 :] if line.startswith(("* ", "- "))]


@dataclass(frozen=True)
class Release:
    version: str
    page: str
    notes: list[str] = field(default_factory=list)
    archive: str | None = None
    """Download URL of this platform's ZIP, or None when the release has none."""
    checksum: str | None = None
    size: int = 0


def parse_release(data: dict[str, Any], platform: str | None) -> Release | None:
    """The release of the GitHub API answer, or None when it is not a version release."""
    if data.get("draft") or data.get("prerelease"):
        return None
    version = str(data.get("tag_name", "")).removeprefix("v")
    if parse_version(version) is None:
        return None
    assets = {str(a.get("name")): a for a in data.get("assets") or []}
    zip_name = f"{NAME}-{version}-{platform}.zip"
    archive = assets.get(zip_name)
    checksum = assets.get(zip_name + ".sha256")
    usable = platform is not None and archive is not None and checksum is not None
    return Release(
        version=version,
        page=str(data.get("html_url", "")),
        notes=whats_new(str(data.get("body") or "")),
        archive=str(archive["browser_download_url"]) if usable and archive else None,
        checksum=str(checksum["browser_download_url"]) if usable and checksum else None,
        size=int(archive.get("size") or 0) if usable and archive else 0,
    )


def _open(url: str, timeout: float) -> Any:
    request = urllib.request.Request(  # noqa: S310 (https GitHub URLs, or file: in tests)
        url, headers={"User-Agent": f"{NAME}/{__version__}", "Accept": "application/json"}
    )
    return urllib.request.urlopen(request, timeout=timeout)  # noqa: S310


def fetch_latest(url: str | None = None, timeout: float = CHECK_TIMEOUT_S) -> Release | None:
    """The latest release (VIDEOFLOW_UPDATE_URL replaces the GitHub API URL for tests)."""
    url = url or os.environ.get("VIDEOFLOW_UPDATE_URL") or LATEST_URL
    with _open(url, timeout) as response:
        return parse_release(json.loads(response.read()), platform_key())


def updates_dir() -> Path:
    """Downloaded updates and replaced files, beside the executable."""
    return application_dir() / UPDATES


def can_install() -> str | None:
    """Why this app cannot update itself, or None when it can."""
    if not getattr(sys, "frozen", False):
        return "Running from source: update with git and the install script"
    if platform_key() is None:
        return "No release is built for this system"
    folder = updates_dir()
    try:
        folder.mkdir(exist_ok=True)
        probe = folder / f".write-{os.getpid()}"
        probe.write_bytes(b"")
        probe.unlink()
    except OSError:
        return f"The application folder is not writable: {application_dir()}"
    return None


def check(release: Release | None, current: str = __version__) -> dict[str, Any]:
    """What the start-up check and Settings show."""
    newer = release is not None and is_newer(release.version, current)
    reason = can_install()
    if newer and reason is None and release is not None and release.archive is None:
        reason = "The release has no download for this system"
    return {
        "current": current,
        "release": asdict(release) if release else None,
        "newer": newer,
        "installable": newer and reason is None,
        "reason": reason if newer else None,
    }


# Download -------------------------------------------------------------------------------


def download(
    release: Release,
    target: Path,
    progress: Progress,
    cancel: threading.Event,
    timeout: float = 60,
) -> Path:
    """Download, verify and unpack the release; returns its unpacked application folder."""
    if release.archive is None or release.checksum is None:
        raise ValueError("The release has no download for this system")
    with _open(release.checksum, timeout) as response:
        expected = response.read().decode("utf-8", "replace").split()[0].lower()
    if not re.fullmatch(r"[0-9a-f]{64}", expected):
        raise ValueError("The release checksum file is not valid")
    shutil.rmtree(target, ignore_errors=True)
    target.mkdir(parents=True)
    archive = target / "release.zip"
    digest = hashlib.sha256()
    done = 0
    with _open(release.archive, timeout) as response, archive.open("wb") as out:
        total = release.size or int(response.headers.get("Content-Length") or 0)
        while chunk := response.read(1 << 20):
            if cancel.is_set():
                raise InterruptedError("Update download cancelled")
            out.write(chunk)
            digest.update(chunk)
            done += len(chunk)
            if total:
                progress(min(0.9, done / total * 0.9), "Downloading the update")
    if digest.hexdigest() != expected:
        raise ValueError("The downloaded update does not match its checksum; nothing changed")
    progress(0.92, "Unpacking the update")
    unpacked = target / "files"
    with zipfile.ZipFile(archive) as bundle:
        for info in bundle.infolist():
            path = (unpacked / info.filename).resolve()
            if not path.is_relative_to(unpacked.resolve()):
                raise ValueError(f"Unsafe path in the update: {info.filename}")
            bundle.extract(info, unpacked)
            mode = (info.external_attr >> 16) & 0o777
            if mode and not info.is_dir():
                path.chmod(mode)
    archive.unlink()
    app = unpacked / NAME
    if not (app / executable_name()).is_file() or not (app / "_internal").is_dir():
        raise ValueError("The update does not contain the Video-Flow application")
    progress(1.0, "Update ready")
    return app


def _detached(command: list[str], cwd: Path) -> None:
    """Start a process that outlives this one."""
    if sys.platform == "win32":
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
        subprocess.Popen(command, creationflags=flags, close_fds=True, cwd=cwd)  # noqa: S603
    else:
        subprocess.Popen(command, start_new_session=True, close_fds=True, cwd=cwd)  # noqa: S603


def start_apply(app: Path, target: Path, pid: int) -> None:
    """Start the downloaded version's `apply-update`, detached from this process."""
    exe = str(app / executable_name())
    _detached([exe, "apply-update", "--target", str(target), "--pid", str(pid)], app)


# Apply (run by the new version) -----------------------------------------------------------


def _alive(pid: int) -> bool:
    if sys.platform == "win32":
        import ctypes

        kernel = ctypes.windll.kernel32  # type: ignore[attr-defined]
        handle = kernel.OpenProcess(0x00100000, False, pid)  # SYNCHRONIZE
        if not handle:
            return False
        try:
            return bool(kernel.WaitForSingleObject(handle, 0) == 0x102)  # WAIT_TIMEOUT
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def wait_exit(pid: int, timeout: float = WAIT_EXIT_S) -> None:
    deadline = time.monotonic() + timeout
    while _alive(pid):
        if time.monotonic() > deadline:
            raise TimeoutError("Video-Flow did not close; the update was not applied")
        time.sleep(0.2)


def _remove(path: Path) -> None:
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    elif path.exists() or path.is_symlink():
        path.unlink()


def replace_files(source: Path, target: Path) -> Path:
    """Move the old application files aside, copy the new ones; returns the backup folder.

    Only the entries of the new application folder are replaced: models, tools, cache,
    settings and logs beside the executable are kept. On failure the old files come back.
    """
    backup = target / UPDATES / f"previous-{time.strftime('%Y%m%d-%H%M%S')}"
    backup.mkdir(parents=True, exist_ok=True)
    moved: list[str] = []
    copied: list[str] = []
    try:
        for item in sorted(source.iterdir()):
            old = target / item.name
            if old.exists() or old.is_symlink():
                shutil.move(str(old), str(backup / item.name))
                moved.append(item.name)
            copied.append(item.name)  # before copying: a partial copy is removed too
            if item.is_dir():
                shutil.copytree(item, old, symlinks=True)
            else:
                shutil.copy2(item, old)
    except Exception:
        for name in copied:
            with contextlib.suppress(OSError):
                _remove(target / name)
        for name in moved:
            with contextlib.suppress(OSError):
                shutil.move(str(backup / name), str(target / name))
        raise
    return backup


def launch(executable: Path) -> None:
    _detached([str(executable)], executable.parent)


def apply(source: Path, target: Path, pid: int, relaunch: Callable[[Path], None] = launch) -> None:
    """Wait for the old app to close, replace its files, start the updated app."""
    wait_exit(pid)
    try:
        replace_files(source, target)
    except Exception:
        log.exception("Update failed; the previous version was kept")
        relaunch(target / executable_name())
        raise
    relaunch(target / executable_name())


def cleanup(app_dir: Path | None = None) -> None:
    """Delete downloaded updates and replaced files, unless this app runs from there."""
    folder = (app_dir or application_dir()) / UPDATES
    running = Path(sys.executable).resolve()
    if folder.is_dir() and not running.is_relative_to(folder.resolve()):
        shutil.rmtree(folder, ignore_errors=True)
