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
NOTES = "docs/release_notes.md"
TEMPLATE = ".github/release-notes-template.md"
TYPES = ("FEATURE", "IMPROVEMENT", "FIX", "DEV")
"""Entry types of docs/release_notes.md; GitHub notes list them in this order, without DEV."""
SECTION = re.compile(r"^## (\d+\.\d+\.\d+)(?: [^\n]*)?$", re.MULTILINE)
ENTRY = re.compile(r"^- (FEATURE|IMPROVEMENT|FIX|DEV): (\S.*)$")
NOTHING_NEW = "Maintenance release: no visible change."


def _key(value: str) -> tuple[int, ...]:
    return tuple(int(part) for part in value.split("."))


def parse_notes(text: str) -> dict[str, list[tuple[str, str]]]:
    """Entries per version of docs/release_notes.md, as (type, text), in file order.

    Every line of a version section must be blank or `- TYPE: text`.
    """
    result: dict[str, list[tuple[str, str]]] = {}
    sections = list(SECTION.finditer(text))
    for index, section in enumerate(sections):
        end = sections[index + 1].start() if index + 1 < len(sections) else len(text)
        entries = []
        for line in text[section.end() : end].splitlines():
            if not line.strip():
                continue
            match = ENTRY.match(line.strip())
            if not match:
                raise ValueError(
                    f"Release notes {section[1]}: '{line.strip()}' must read "
                    f"'- TYPE: text' with TYPE in {', '.join(TYPES)}"
                )
            entries.append((match[1], match[2].strip()))
        if not entries:
            raise ValueError(f"Release notes {section[1]} have no entry")
        result[section[1]] = entries
    return result


def previous_release(current: str, released: list[str]) -> str | None:
    """The newest published version older than `current` (from tags such as v1.2.3)."""
    versions = [
        tag.removeprefix("v")
        for tag in released
        if re.fullmatch(r"v?\d+\.\d+\.\d+", tag.strip())
    ]
    older = [v for v in versions if _key(v) < _key(current)]
    return max(older, key=_key) if older else None


def release_notes(current: str, released: list[str], root: Path | None = None) -> str:
    """GitHub release body: the template, with the user-facing entries of every version
    after the previous release up to `current` (FEATURE, then IMPROVEMENT, then FIX)."""
    root = root or ROOT
    notes = parse_notes((root / NOTES).read_text(encoding="utf-8"))
    since = previous_release(current, released)
    versions = [
        v
        for v in notes
        if _key(v) <= _key(current) and (since is None or _key(v) > _key(since))
    ]
    lines = [
        f"* {text}"
        for kind in TYPES[:-1]
        for v in versions
        for entry_kind, text in notes[v]
        if entry_kind == kind
    ]
    template = (root / TEMPLATE).read_text(encoding="utf-8")
    return template.replace("{whats_new}", "\n".join(lines) or f"* {NOTHING_NEW}")


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
    notes = parse_notes((root / NOTES).read_text(encoding="utf-8"))
    if value not in notes:
        raise ValueError(f"No release notes for {value}")
    if "{whats_new}" not in (root / TEMPLATE).read_text(encoding="utf-8"):
        raise ValueError(f"{TEMPLATE} has no {{whats_new}} placeholder")
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


def verify(released: list[str] | None = None) -> None:
    value = version()
    for platform in PLATFORMS:
        path = ROOT / "dist" / f"Video-Flow-{value}-{platform}.zip"
        checksum = (
            path.with_suffix(".zip.sha256").read_text(encoding="utf-8").split()[0]
        )
        with path.open("rb") as stream:
            if hashlib.file_digest(stream, "sha256").hexdigest() != checksum:
                raise ValueError(f"Checksum mismatch: {path.name}")
    body = release_notes(value, released or [])
    (ROOT / "notes.md").write_text(body, encoding="utf-8")
    print(body)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("metadata", "archive", "verify"))
    parser.add_argument("--platform", choices=PLATFORMS)
    parser.add_argument(
        "--released",
        nargs="*",
        default=[],
        help="Tags of the published GitHub releases (verify): notes start after the newest",
    )
    args = parser.parse_args()
    if args.command == "metadata":
        metadata()
    elif args.command == "verify":
        verify(args.released)
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
