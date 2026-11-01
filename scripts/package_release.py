"""Build the one-folder desktop app and update releases/Video-Flow in place.

PyInstaller empties its output folder, which would delete what lives beside the
executable: models/, tools/, templates/, settings.json and logs. The app is therefore
built into a staging folder, and only the files PyInstaller produces (the executable
and _internal/) replace their previous versions in releases/Video-Flow.

The executable embeds every Python module (Video-Flow's and its dependencies'), so it
is rebuilt only when Python code, installed packages, bundled assets or the spec
change. When only the interface changed, the built frontend is copied into
_internal/frontend/dist and PyInstaller does not run. `--full` forces a rebuild.

Run from the repository root through scripts/dev.sh package or scripts/dev.ps1 package.
"""

import hashlib
import importlib.metadata
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NAME = "Video-Flow"
STAGING = ROOT / ".cache" / "pyinstaller"
RELEASE = ROOT / "releases" / NAME
STAMP = "build-inputs.txt"
"""Fingerprint of the inputs of the last full build, kept in _internal/."""


def inputs_fingerprint() -> str:
    """Everything the executable and _internal depend on, except the built frontend."""
    digest = hashlib.sha256()
    files = [
        *sorted((ROOT / "backend" / "videoflow").rglob("*")),
        *sorted((ROOT / "assets").rglob("*")),
        ROOT / "scripts" / "desktop.spec",
        ROOT / "docs" / "reference" / "desktop-runtime.md",
    ]
    for path in files:
        if path.is_file() and "__pycache__" not in path.parts:
            digest.update(path.relative_to(ROOT).as_posix().encode())
            digest.update(path.read_bytes())
    packages = sorted(
        f"{d.metadata['Name']}=={d.version}" for d in importlib.metadata.distributions()
    )
    digest.update("\n".join(packages).encode())
    return digest.hexdigest()


def sync_frontend() -> None:
    target = RELEASE / "_internal" / "frontend" / "dist"
    shutil.rmtree(target, ignore_errors=True)
    shutil.copytree(ROOT / "frontend" / "dist", target)


def build() -> int:
    """Full PyInstaller build into staging, then replace the app files of the release."""
    built = STAGING / "dist" / NAME
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--distpath",
        str(STAGING / "dist"),
        "--workpath",
        str(STAGING / "work"),
        str(ROOT / "scripts" / "desktop.spec"),
    ]
    result = subprocess.run(command, cwd=ROOT, check=False)
    if result.returncode:
        return result.returncode
    RELEASE.mkdir(parents=True, exist_ok=True)
    produced = sorted(built.iterdir())
    names = {item.name for item in produced}
    for item in produced:
        target = RELEASE / item.name
        try:
            if target.is_dir():
                shutil.rmtree(target)
            elif target.exists():
                target.unlink()
        except PermissionError:
            print(f"Cannot replace {target}: close Video-Flow and package again.", file=sys.stderr)
            return 1
        shutil.move(str(item), str(target))
    kept = sorted(p.name for p in RELEASE.iterdir() if p.name not in names)
    print(f"Updated {RELEASE}" + (f" (kept: {', '.join(kept)})" if kept else ""))
    return 0


def main() -> int:
    started = time.monotonic()
    fingerprint = inputs_fingerprint()
    stamp = RELEASE / "_internal" / STAMP
    executable = RELEASE / (NAME + (".exe" if sys.platform == "win32" else ""))
    current = stamp.is_file() and stamp.read_text(encoding="utf-8").strip() == fingerprint
    if "--full" not in sys.argv[1:] and current and executable.is_file():
        try:
            sync_frontend()
        except PermissionError:
            print("Cannot update the interface: close Video-Flow and package again.", file=sys.stderr)
            return 1
        print(
            f"App code unchanged: updated the interface only ({time.monotonic() - started:.0f} s)."
            " Use --full to rebuild everything."
        )
        return 0
    code = build()
    if code == 0:
        stamp.write_text(fingerprint + "\n", encoding="utf-8")
        print(
            f"Full build {time.monotonic() - started:.0f} s. PyInstaller reuses its dependency"
            " analysis unless Python code, packages or the spec changed ('Building because ...')."
        )
    return code


if __name__ == "__main__":
    sys.exit(main())
