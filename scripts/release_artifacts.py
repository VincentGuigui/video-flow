"""Version metadata and portable ZIP artifacts for the release workflow."""

import argparse
import hashlib
import json
import os
import re
import stat
import sys
import tomllib
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLATFORMS = ("windows-x64", "linux-x64")


def version(root: Path = ROOT) -> str:
    value = tomllib.loads(
        (root / "backend/pyproject.toml").read_text(encoding="utf-8")
    )["project"]["version"]
    if not re.fullmatch(r"\d+\.\d+\.\d+", value):
        raise ValueError("Release version must have the form MAJOR.MINOR.PATCH")
    init = (root / "backend/videoflow/__init__.py").read_text(encoding="utf-8")
    match = re.search(r'__version__ = "([^"]+)"', init)
    front = json.loads((root / "frontend/package.json").read_text(encoding="utf-8"))
    lock = json.loads((root / "frontend/package-lock.json").read_text(encoding="utf-8"))
    if not match or {
        match[1],
        front["version"],
        lock["version"],
        lock["packages"][""]["version"],
    } != {value}:
        raise ValueError("Backend, frontend and lockfile versions disagree")
    notes = (root / "docs/release_notes.md").read_text(encoding="utf-8")
    if not re.search(rf"^## {re.escape(value)}(?: |$)", notes, re.MULTILINE):
        raise ValueError(f"No release notes for {value}")
    return value


def metadata() -> None:
    value = version()
    tag = "v" + value
    if (
        os.environ.get("GITHUB_REF_TYPE") == "tag"
        and os.environ.get("GITHUB_REF_NAME") != tag
    ):
        raise ValueError(f"Tag must match application version: {tag}")
    data = {
        "version": value,
        "tag": tag,
        "name": f"Video-Flow {value}",
        "sha": os.environ.get("GITHUB_SHA", ""),
    }
    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with Path(output).open("a", encoding="utf-8") as stream:
            stream.writelines(f"{key}={item}\n" for key, item in data.items())
    print(json.dumps(data))


def archive(platform: str, root: Path = ROOT) -> Path:
    if platform not in PLATFORMS:
        raise ValueError("Unsupported release platform")
    value = version(root)
    folder = root / "releases/Video-Flow"
    executable = "Video-Flow.exe" if platform == "windows-x64" else "Video-Flow"
    for name in (
        executable,
        "_internal/frontend/dist/index.html",
        "_internal/build-inputs.txt",
    ):
        if not (folder / name).is_file():
            raise ValueError(f"Incomplete release: missing {name}")
    if (
        platform == "linux-x64"
        and sys.platform != "win32"
        and not (folder / executable).stat().st_mode & stat.S_IXUSR
    ):
        raise ValueError("Linux executable is missing its execute permission")
    target = root / f"Video-Flow-{value}-{platform}.zip"
    with zipfile.ZipFile(
        target, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6
    ) as stream:
        for path in sorted(folder.rglob("*")):
            if path.is_file():
                stream.write(path, path.relative_to(folder.parent).as_posix())
    if target.stat().st_size >= 2 * 1024**3:
        raise ValueError("ZIP exceeds GitHub's 2 GiB per-asset limit")
    with zipfile.ZipFile(target) as stream:
        bad = stream.testzip()
        if bad:
            raise ValueError(f"Corrupt ZIP member: {bad}")
    with target.open("rb") as source:
        checksum = hashlib.file_digest(source, "sha256").hexdigest()
    target.with_suffix(".zip.sha256").write_text(
        f"{checksum}  {target.name}\n", encoding="utf-8"
    )
    print(target)
    return target


def verify() -> None:
    value = version()
    for platform in PLATFORMS:
        path = ROOT / "dist" / f"Video-Flow-{value}-{platform}.zip"
        checksum = (
            path.with_suffix(".zip.sha256").read_text(encoding="utf-8").split()[0]
        )
        with path.open("rb") as stream:
            if hashlib.file_digest(stream, "sha256").hexdigest() != checksum:
                raise ValueError(f"Checksum mismatch: {path.name}")
    notes = (ROOT / "docs/release_notes.md").read_text(encoding="utf-8")
    body = re.split(
        rf"^## {re.escape(value)}(?: [^\n]*)?\n", notes, maxsplit=1, flags=re.MULTILINE
    )[1]
    body = re.split(r"^## ", body, maxsplit=1, flags=re.MULTILINE)[0].strip()
    body += (
        "\n\nExtract the complete Video-Flow folder before running. "
        "Windows x64 uses DirectML with CPU fallback; Linux x64 uses CPU. "
        "FFmpeg and AI model downloads are offered in the app, on request. "
        "Verify the ZIP against its accompanying SHA-256 file.\n"
    )
    (ROOT / "notes.md").write_text(body, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("metadata", "archive", "verify"))
    parser.add_argument("--platform", choices=PLATFORMS)
    args = parser.parse_args()
    if args.command == "metadata":
        metadata()
    elif args.command == "verify":
        verify()
    elif args.platform:
        archive(args.platform)
    else:
        parser.error("archive requires --platform")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc
