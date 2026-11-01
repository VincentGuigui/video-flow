"""Build the one-folder desktop app and update releases/Video-Flow in place.

PyInstaller empties its output folder, which would delete what lives beside the
executable: models/, tools/, templates/, settings.json and logs. The app is therefore
built into a staging folder, and only the files PyInstaller produces (the executable
and _internal/) replace their previous versions in releases/Video-Flow.

Run from the repository root through scripts/dev.sh package or scripts/dev.ps1 package.
"""

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NAME = "Video-Flow"
STAGING = ROOT / ".cache" / "pyinstaller"
RELEASE = ROOT / "releases" / NAME


def main() -> int:
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


if __name__ == "__main__":
    sys.exit(main())
