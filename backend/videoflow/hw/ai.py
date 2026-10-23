"""AI inference provider probing and session factory (NPU -> GPU -> CPU).

onnxruntime and openvino are imported lazily and optionally: the core works without them.
"""

from __future__ import annotations

import importlib
import platform
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

Prefer = Literal["auto", "npu", "gpu", "cpu"]


class Device(StrEnum):
    NPU = "npu"
    GPU = "gpu"
    CPU = "cpu"


@dataclass(frozen=True)
class ProviderChoice:
    device: Device
    provider: str  # ONNX Runtime execution provider name
    options: dict[str, str] = field(default_factory=dict)

    @property
    def label(self) -> str:
        extra = f":{self.options['device_type']}" if "device_type" in self.options else ""
        return f"{self.provider}{extra}"

    def as_ort_provider(self) -> str | tuple[str, dict[str, str]]:
        return (self.provider, dict(self.options)) if self.options else self.provider


@dataclass(frozen=True)
class SessionAttempt:
    choice: ProviderChoice
    error: str | None  # None means the attempt succeeded


@dataclass
class ModelSession:
    """A validated inference session plus how it was obtained."""

    session: Any
    choice: ProviderChoice
    attempts: list[SessionAttempt]

    @property
    def device(self) -> Device:
        return self.choice.device


class NoProviderError(RuntimeError):
    pass


def _import_ort() -> Any | None:
    try:
        return importlib.import_module("onnxruntime")
    except Exception:  # noqa: BLE001 - missing or broken native libs
        return None


def _import_openvino() -> Any | None:
    try:
        return importlib.import_module("openvino")
    except Exception:  # noqa: BLE001
        return None


def available_providers() -> list[str]:
    ort = _import_ort()
    return list(ort.get_available_providers()) if ort is not None else []


def openvino_devices() -> list[str] | None:
    """Device names reported by OpenVINO ("CPU", "GPU", "NPU"), or None when it is absent."""
    ov = _import_openvino()
    if ov is None:
        return None
    try:
        return [str(d) for d in ov.Core().available_devices]
    except Exception:  # noqa: BLE001
        return None


def _qnn_options() -> dict[str, str]:
    return {"backend_path": "QnnHtp.dll"}


def build_chain(
    providers: list[str],
    ov_devices: list[str] | None = None,
    prefer: Prefer = "auto",
) -> list[ProviderChoice]:
    """Order the usable providers NPU -> GPU -> CPU.

    `prefer` sets the first tier tried: auto/npu start at the NPU, gpu skips the NPU,
    cpu uses only the CPU. The CPU provider always closes the chain (unless unavailable).
    OpenVINO device entries need `ov_devices` (without the openvino package they are skipped
    because the device list cannot be verified).
    """
    has = set(providers)
    ov = set(ov_devices or [])
    ov_ep = "OpenVINOExecutionProvider" in has
    npu: list[ProviderChoice] = []
    gpu: list[ProviderChoice] = []
    if ov_ep and "NPU" in ov:
        npu.append(ProviderChoice(Device.NPU, "OpenVINOExecutionProvider", {"device_type": "NPU"}))
    if "VitisAIExecutionProvider" in has:
        npu.append(ProviderChoice(Device.NPU, "VitisAIExecutionProvider"))
    if "QNNExecutionProvider" in has:
        npu.append(ProviderChoice(Device.NPU, "QNNExecutionProvider", _qnn_options()))
    if "CUDAExecutionProvider" in has:
        gpu.append(ProviderChoice(Device.GPU, "CUDAExecutionProvider"))
    if "DmlExecutionProvider" in has:
        gpu.append(ProviderChoice(Device.GPU, "DmlExecutionProvider"))
    if ov_ep and "GPU" in ov:
        gpu.append(ProviderChoice(Device.GPU, "OpenVINOExecutionProvider", {"device_type": "GPU"}))
    for name in ("ROCMExecutionProvider", "MIGraphXExecutionProvider"):
        if name in has:
            gpu.append(ProviderChoice(Device.GPU, name))
    cpu = (
        [ProviderChoice(Device.CPU, "CPUExecutionProvider")]
        if "CPUExecutionProvider" in has
        else []
    )
    if prefer == "cpu":
        return cpu
    if prefer == "gpu":
        return [*gpu, *cpu]
    return [*npu, *gpu, *cpu]


def probe_chain(prefer: Prefer = "auto") -> list[ProviderChoice]:
    return build_chain(available_providers(), openvino_devices(), prefer)


_ORT_DTYPES = {
    "tensor(float)": "float32", "tensor(float16)": "float16", "tensor(double)": "float64",
    "tensor(int64)": "int64", "tensor(int32)": "int32", "tensor(int8)": "int8",
    "tensor(uint8)": "uint8", "tensor(bool)": "bool",
}  # fmt: skip


def _warmup(session: Any, dynamic_dim: int = 1) -> None:
    """Run the model once on zero inputs so unsupported operators surface now."""
    import numpy as np

    feeds: dict[str, Any] = {}
    for inp in session.get_inputs():
        shape = [d if isinstance(d, int) and d > 0 else dynamic_dim for d in inp.shape]
        feeds[inp.name] = np.zeros(shape, dtype=_ORT_DTYPES.get(inp.type, "float32"))
    session.run(None, feeds)


def make_session(
    model_path: str | Path,
    prefer: Prefer = "auto",
    *,
    warmup: bool = True,
    sess_options: Any | None = None,
    chain: list[ProviderChoice] | None = None,
) -> ModelSession:
    """Create an InferenceSession on the best provider that creates and warms up cleanly.

    Each model walks the chain independently, so one model's unsupported operator does not
    demote the others. Raises NoProviderError when onnxruntime is absent or nothing works.
    """
    ort = _import_ort()
    if ort is None:
        raise NoProviderError(
            "onnxruntime is not installed (install a videoflow accelerator extra)"
        )
    candidates = chain if chain is not None else probe_chain(prefer)
    attempts: list[SessionAttempt] = []
    for choice in candidates:
        try:
            opts = sess_options if sess_options is not None else ort.SessionOptions()
            sess = ort.InferenceSession(
                str(model_path), sess_options=opts, providers=[choice.as_ort_provider()]
            )
            # ORT silently falls back to CPU when a provider fails to initialise.
            active = sess.get_providers()
            if not active or active[0] != choice.provider:
                raise RuntimeError(f"provider not active (got {active})")
            if warmup:
                _warmup(sess)
        except Exception as exc:  # noqa: BLE001 - any provider failure means try the next
            attempts.append(SessionAttempt(choice, f"{type(exc).__name__}: {exc}"))
            continue
        attempts.append(SessionAttempt(choice, None))
        return ModelSession(sess, choice, attempts)
    detail = "; ".join(f"{a.choice.label}: {a.error}" for a in attempts) or "no provider available"
    raise NoProviderError(f"no working provider for {model_path}: {detail}")


def describe_ai() -> dict[str, object]:
    """Doctor data: runtime presence, providers, OpenVINO devices and the resolved chain."""
    ort = _import_ort()
    return {
        "onnxruntime": getattr(ort, "__version__", None) if ort is not None else None,
        "providers": available_providers(),
        "openvino_devices": openvino_devices(),
        "chain": [c.label for c in probe_chain("auto")],
        "machine": platform.machine(),
    }
