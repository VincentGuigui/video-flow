"""FFmpeg capability probe: version, graph-file flag, xfade names, filters, encoders, hwaccels."""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

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
    """Run the capability probe (about 6 short ffmpeg invocations)."""
    b = binaries or locate_binaries()
    base = [str(b.ffmpeg), "-hide_banner"]

    def out(*extra: str) -> str:
        env_proc = run_sync([*base, *extra])
        return env_proc.stdout.decode("utf-8", "replace")

    version_text = out("-version")
    if not version_text:
        raise RuntimeError(f"cannot execute {b.ffmpeg}")
    version, tup = parse_version(version_text)
    return FFmpegCaps(
        ffmpeg=b.ffmpeg,
        ffprobe=b.ffprobe,
        version=version,
        version_tuple=tup,
        graph_flag=detect_graph_flag(b.ffmpeg),
        xfade_transitions=parse_xfade(out("-h", "filter=xfade")),
        filters=parse_table(out("-filters")),
        encoders=parse_table(out("-encoders")),
        hwaccels=parse_hwaccels(out("-hwaccels")),
    )


_cached: FFmpegCaps | None = None


def get_caps(refresh: bool = False) -> FFmpegCaps:
    """Process-wide cached probe using default binary discovery."""
    global _cached
    if _cached is None or refresh:
        _cached = probe_caps()
    return _cached


__all__ = [
    "GRAPH_FLAG_NEW", "GRAPH_FLAG_OLD", "FFmpegBinaries", "FFmpegCaps", "detect_graph_flag",
    "get_caps", "locate_binaries", "probe_caps", "run_sync",
]  # fmt: skip
