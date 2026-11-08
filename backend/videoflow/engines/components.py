"""Explicit installation of fixed inference components in a source environment.

Frozen releases carry Python runtimes and must be replaced if incomplete. No API
argument becomes a package name, executable path, shell command or install target.
"""

import asyncio
import importlib.metadata
import importlib.util
import shutil
import sys
from typing import Any

from videoflow.hw.ai import cuda_status
from videoflow.preferences import Preferences
from videoflow.runtime import application_dir

COMPONENTS = {
    "speech": (
        "ONNX speech and similarity",
        ("onnxruntime", "onnx_asr", "huggingface_hub", "tokenizers"),
        ("onnx-asr>=0.7", "huggingface-hub>=0.25", "tokenizers>=0.20"),
    ),
    "qwen": (
        "Qwen runtime",
        ("torch", "transformers", "safetensors"),
        ("torch==2.14.1", "transformers==4.57.6", "safetensors==0.8.0"),
    ),
    "whisper": (
        "Whisper runtime",
        ("faster_whisper", "ctranslate2", "av"),
        ("faster-whisper==1.2.1", "ctranslate2==4.8.3", "av==19.0.2"),
    ),
}


def uv_path() -> str | None:
    local = (
        application_dir() / "tools" / "uv" / "bin" / ("uv.exe" if sys.platform == "win32" else "uv")
    )
    return str(local) if local.is_file() else shutil.which("uv")


def missing_modules(modules: tuple[str, ...]) -> list[str]:
    return [name for name in modules if importlib.util.find_spec(name) is None]


def install_command(component: str) -> list[str]:
    if getattr(sys, "frozen", False):
        raise ValueError(
            "This packaged app is incomplete. Reinstall a complete Video-Flow release."
        )
    uv = uv_path()
    if uv is None:
        raise ValueError("The uv installer is missing. Run the Video-Flow installer first.")
    command = [uv, "pip", "install", "--python", sys.executable]
    if component == "cuda":
        version = importlib.metadata.version("onnxruntime-gpu")
        return [*command, f"onnxruntime-gpu[cuda,cudnn]=={version}"]
    if component not in COMPONENTS:
        raise ValueError("Unknown runtime component")
    packages = list(COMPONENTS[component][2])
    if component == "speech" and importlib.util.find_spec("onnxruntime") is None:
        packages.append("onnxruntime>=1.20")
    # faster-whisper declares the CPU ORT wheel even when a compatible GPU/DML
    # variant is installed. Its other direct dependencies are already in speech.
    if component == "whisper":
        command.append("--no-deps")
    return [*command, *packages]


class Components:
    def __init__(self, *, native: bool) -> None:
        self.native = native
        self.job: dict[str, Any] | None = None
        self.task: asyncio.Task[None] | None = None
        self.process: asyncio.subprocess.Process | None = None

    def status(self, preferences: Preferences) -> dict[str, Any]:
        selected = ["speech"]
        if preferences.asr_engine == "faster-whisper":
            selected.append("whisper")
        if preferences.summary_engine == "qwen":
            selected.append("qwen")
        installable = self.native and not getattr(sys, "frozen", False) and uv_path() is not None
        rows = []
        for key in selected:
            name, modules, _ = COMPONENTS[key]
            missing = missing_modules(modules)
            rows.append(
                {
                    "id": key,
                    "name": name,
                    "missing": missing,
                    "available": not missing,
                    "optional": False,
                    "detail": ", ".join(missing),
                    "installable": installable,
                }
            )
        if preferences.ai_device != "cpu":
            cuda = cuda_status()
            if cuda is not None:
                rows.append(
                    {
                        "id": "cuda",
                        "name": "NVIDIA CUDA acceleration",
                        "missing": [],
                        "available": cuda["available"],
                        "optional": True,
                        "detail": cuda["detail"],
                        "installable": installable,
                    }
                )
        return {
            "components": rows,
            "job": dict(self.job) if self.job else None,
            "packaged": bool(getattr(sys, "frozen", False)),
        }

    def start(self, component: str) -> dict[str, Any]:
        if not self.native:
            raise ValueError("Component installation is only available in the desktop app")
        if self.task is not None and not self.task.done():
            raise ValueError("A component installation is already running")
        command = install_command(component)
        self.job = {
            "component": component,
            "state": "running",
            "phase": "Installing dependencies…",
            "error": None,
            "restartRequired": False,
        }

        async def run() -> None:
            assert self.job is not None
            try:
                process_options: dict[str, Any] = (
                    {"creationflags": 0x08000000} if sys.platform == "win32" else {}
                )
                self.process = await asyncio.create_subprocess_exec(
                    *command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT,
                    **process_options,
                )
                assert self.process.stdout is not None
                tail = ""
                while line := await self.process.stdout.readline():
                    text = line.decode(errors="replace").strip()
                    tail = (tail + "\n" + text)[-4000:]
                    if text:
                        self.job["phase"] = text[-400:]
                code = await self.process.wait()
                if code:
                    raise RuntimeError(tail.strip() or f"Installer exited with code {code}")
                self.job.update(
                    state="done",
                    phase="Installed. Restart Video-Flow before analysis.",
                    restartRequired=True,
                )
            except asyncio.CancelledError:
                self.job.update(state="cancelled", phase="Installation cancelled")
                raise
            except Exception as exc:
                self.job.update(state="failed", error=str(exc))
            finally:
                if self.process is not None and self.process.returncode is None:
                    self.process.kill()
                    await self.process.wait()
                self.process = None

        self.task = asyncio.create_task(run())
        return dict(self.job)

    async def close(self) -> None:
        if self.task is not None and not self.task.done():
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
