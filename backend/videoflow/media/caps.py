"""FFmpeg capability probe: version, graph-file flag, xfade names, filters, encoders, hwaccels."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

GRAPH_FLAG_NEW = "-/filter_complex"
GRAPH_FLAG_OLD = "-filter_complex_script"

_VERSION_RE = re.compile(r"version\s+[nN]?(\d+)\.(\d+)(?:\.(\d+))?")
_XFADE_RE = re.compile(r"^\s+(\w+)\s+-?\d+\s+\.\.F")
_TABLE_RE = re.compile(r"^\s*[A-Z.|]{3,6}\s+([\w.\-]+)\s")


NO_WINDOW: int = getattr(subprocess, "CREATE_NO_WINDOW", 0)  # Windows only


def run_sync(
    args: list[str], timeout: float = 20.0, input_bytes: bytes | None = None
) -> subprocess.CompletedProcess[bytes]:
    """Run a short command without a console window on Windows. Never raises on failure."""
    try:
        return subprocess.run(  # noqa: S603
            args,
            input=input_bytes,
            capture_output=True,
            timeout=timeout,
            check=False,
            creationflags=NO_WINDOW,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return subprocess.CompletedProcess(args, 127, b"", str(exc).encode())


@dataclass(frozen=True)
class FFmpegBinaries:
    ffmpeg: Path
    ffprobe: Path


def _repo_tools_dir() -> Path:
    return Path(__file__).resolve().parents[3] / "tools" / "ffmpeg"


def _exe(name: str) -> str:
    return f"{name}.exe" if sys.platform == "win32" else name


def _find_in_dir(directory: Path, name: str) -> Path | None:
    for sub in (directory, directory / "bin"):
        candidate = sub / _exe(name)
        if candidate.is_file():
            return candidate
    return None


def locate_binaries(
    ffmpeg: Path | str | None = None,
    ffprobe: Path | str | None = None,
    tools_dir: Path | None = None,
) -> FFmpegBinaries:
    """Resolve ffmpeg/ffprobe: settings override, then tools/ffmpeg/, then PATH.

    An override may be a file or a directory holding both binaries.
    Raises FileNotFoundError when a binary cannot be found.
    """
    tools = tools_dir if tools_dir is not None else _repo_tools_dir()
    found: dict[str, Path] = {}
    for name, override in (("ffmpeg", ffmpeg), ("ffprobe", ffprobe)):
        path: Path | None = None
        if override:
            p = Path(override)
            path = _find_in_dir(p, name) if p.is_dir() else (p if p.is_file() else None)
            if path is None:
                raise FileNotFoundError(f"{name} override not found: {p}")
        if path is None and ffmpeg and Path(ffmpeg).is_dir():
            path = _find_in_dir(Path(ffmpeg), name)
        path = path or _find_in_dir(tools, name)
        if path is None:
            on_path = shutil.which(name)
            path = Path(on_path) if on_path else None
        if path is None:
            raise FileNotFoundError(f"{name} not found (settings, tools/ffmpeg/, PATH)")
        found[name] = path
    return FFmpegBinaries(found["ffmpeg"], found["ffprobe"])


@dataclass(frozen=True)
class FFmpegCaps:
    ffmpeg: Path
    ffprobe: Path
    version: str
    version_tuple: tuple[int, int, int]
    graph_flag: str
    xfade_transitions: frozenset[str] = field(default_factory=frozenset)
    filters: frozenset[str] = field(default_factory=frozenset)
    encoders: frozenset[str] = field(default_factory=frozenset)
    hwaccels: frozenset[str] = field(default_factory=frozenset)

    def has_filter(self, name: str) -> bool:
        return name in self.filters

    def has_encoder(self, name: str) -> bool:
        return name in self.encoders

    def supports_xfade(self, name: str) -> bool:
        return name in self.xfade_transitions

    def to_dict(self) -> dict[str, object]:
        return {
            "ffmpeg": str(self.ffmpeg),
            "ffprobe": str(self.ffprobe),
            "version": self.version,
            "graph_flag": self.graph_flag,
            "xfade_transitions": sorted(self.xfade_transitions),
            "hwaccels": sorted(self.hwaccels),
            "encoders": sorted(self.encoders),
            "n_filters": len(self.filters),
        }


def parse_version(text: str) -> tuple[str, tuple[int, int, int]]:
    """Return (version string, numeric tuple) from `ffmpeg -version`; git builds give (0, 0, 0)."""
    first = text.splitlines()[0] if text else ""
    m = _VERSION_RE.search(first)
    token = first.split("version", 1)[1].split()[0] if "version" in first else "unknown"
    if not m:
        return token, (0, 0, 0)
    return token, (int(m[1]), int(m[2]), int(m[3] or 0))


def parse_table(text: str) -> frozenset[str]:
    """Names from `-filters` / `-encoders` tables; legend lines never match the row pattern."""
    return frozenset(m[1] for line in text.splitlines() if (m := _TABLE_RE.match(line)))


def parse_xfade(text: str) -> frozenset[str]:
    names: set[str] = set()
    in_transition = False
    for line in text.splitlines():
        if line.strip().startswith("transition "):
            in_transition = True
            continue
        if in_transition:
            m = _XFADE_RE.match(line)
            if m:
                names.add(m[1])
            elif line.strip().startswith("duration"):
                break
    return frozenset(names)


def parse_hwaccels(text: str) -> frozenset[str]:
    lines = text.splitlines()
    return (
        frozenset(s for line in lines[1:] if (s := line.strip()) and not s.endswith(":"))
        if lines
        else frozenset()
    )


def detect_graph_flag(ffmpeg: Path) -> str:
    """Use `-/filter_complex <file>` when this build accepts it, else `-filter_complex_script`."""
    with tempfile.TemporaryDirectory(prefix="vf-caps-") as tmp:
        graph = Path(tmp) / "g.txt"
        graph.write_text("[0:v]null[o]", encoding="utf-8")
        proc = run_sync(
            [
                str(ffmpeg),
                "-hide_banner",
                "-v",
                "error",
                "-nostdin",
                "-f",
                "lavfi",
                "-i",
                "nullsrc=s=16x16:d=0.1",
                GRAPH_FLAG_NEW,
                str(graph),
                "-map",
                "[o]",
                "-frames:v",
                "1",
                "-f",
                "null",
                "-",
            ]  # fmt: skip
        )
    return GRAPH_FLAG_NEW if proc.returncode == 0 else GRAPH_FLAG_OLD


def probe_caps(binaries: FFmpegBinaries | None = None) -> FFmpegCaps:
    """Run the capability probe: six short ffmpeg invocations, side by side."""
    b = binaries or locate_binaries()
    base = [str(b.ffmpeg), "-hide_banner"]

    def out(*extra: str) -> str:
        env_proc = run_sync([*base, *extra])
        return env_proc.stdout.decode("utf-8", "replace")

    with ThreadPoolExecutor(max_workers=6, thread_name_prefix="ffmpeg-caps") as pool:
        version_text = pool.submit(out, "-version")
        graph_flag = pool.submit(detect_graph_flag, b.ffmpeg)
        xfade = pool.submit(out, "-h", "filter=xfade")
        filters = pool.submit(out, "-filters")
        encoders = pool.submit(out, "-encoders")
        hwaccels = pool.submit(out, "-hwaccels")
        if not version_text.result():
            raise RuntimeError(f"cannot execute {b.ffmpeg}")
        version, tup = parse_version(version_text.result())
        return FFmpegCaps(
            ffmpeg=b.ffmpeg,
            ffprobe=b.ffprobe,
            version=version,
            version_tuple=tup,
            graph_flag=graph_flag.result(),
            xfade_transitions=parse_xfade(xfade.result()),
            filters=parse_table(filters.result()),
            encoders=parse_table(encoders.result()),
            hwaccels=parse_hwaccels(hwaccels.result()),
        )


CAPS_CACHE_VERSION = 1


def caps_cache_file() -> Path:
    """Probe results kept between launches, per user (VIDEOFLOW_CAPS_CACHE overrides)."""
    override = os.environ.get("VIDEOFLOW_CAPS_CACHE")
    if override:
        return Path(override)
    from videoflow.runtime import user_data_dir

    return user_data_dir() / "ffmpeg-caps.json"


def _fingerprint(binaries: FFmpegBinaries) -> dict[str, Any] | None:
    """What identifies a build: both paths, sizes and modification times."""
    try:
        result: dict[str, Any] = {"version": CAPS_CACHE_VERSION}
        for name, path in (("ffmpeg", binaries.ffmpeg), ("ffprobe", binaries.ffprobe)):
            stat = path.stat()
            result[name] = [str(path.resolve()), stat.st_size, stat.st_mtime_ns]
        return result
    except OSError:
        return None


def _load_cached(fingerprint: dict[str, Any]) -> FFmpegCaps | None:
    try:
        data = json.loads(caps_cache_file().read_text(encoding="utf-8"))
        if data.get("fingerprint") != fingerprint:
            return None
        caps = data["caps"]
        return FFmpegCaps(
            ffmpeg=Path(caps["ffmpeg"]),
            ffprobe=Path(caps["ffprobe"]),
            version=str(caps["version"]),
            version_tuple=tuple(int(v) for v in caps["version_tuple"]),  # type: ignore[arg-type]
            graph_flag=str(caps["graph_flag"]),
            xfade_transitions=frozenset(caps["xfade_transitions"]),
            filters=frozenset(caps["filters"]),
            encoders=frozenset(caps["encoders"]),
            hwaccels=frozenset(caps["hwaccels"]),
        )
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return None


def _store(caps: FFmpegCaps, fingerprint: dict[str, Any]) -> None:
    data = {
        "fingerprint": fingerprint,
        "caps": {
            "ffmpeg": str(caps.ffmpeg),
            "ffprobe": str(caps.ffprobe),
            "version": caps.version,
            "version_tuple": list(caps.version_tuple),
            "graph_flag": caps.graph_flag,
            "xfade_transitions": sorted(caps.xfade_transitions),
            "filters": sorted(caps.filters),
            "encoders": sorted(caps.encoders),
            "hwaccels": sorted(caps.hwaccels),
        },
    }
    target = caps_cache_file()
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        part = target.with_name(target.name + ".part")
        part.write_text(json.dumps(data), encoding="utf-8")
        os.replace(part, target)
    except OSError:
        pass  # a read-only profile only costs a probe at the next launch


_cached: FFmpegCaps | None = None
_cached_fingerprint: dict[str, Any] | None = None


def get_caps(refresh: bool = False) -> FFmpegCaps:
    """Process-wide capabilities of the default ffmpeg (settings, tools/ffmpeg/, PATH).

    The probe runs only for a build not seen before: its results are kept on disk, keyed
    by the binaries' paths, sizes and dates. `refresh` looks for the binaries again (an
    install or a changed PATH) and probes only if they changed.
    """
    global _cached, _cached_fingerprint
    if _cached is not None and not refresh:
        return _cached
    binaries = locate_binaries()
    fingerprint = _fingerprint(binaries)
    if _cached is not None and fingerprint is not None and fingerprint == _cached_fingerprint:
        return _cached
    caps = _load_cached(fingerprint) if fingerprint is not None else None
    if caps is None:
        caps = probe_caps(binaries)
        if fingerprint is not None:
            _store(caps, fingerprint)
    _cached, _cached_fingerprint = caps, fingerprint
    return caps


__all__ = [
    "GRAPH_FLAG_NEW", "GRAPH_FLAG_OLD", "FFmpegBinaries", "FFmpegCaps", "detect_graph_flag",
    "get_caps", "locate_binaries", "probe_caps", "run_sync",
]  # fmt: skip
