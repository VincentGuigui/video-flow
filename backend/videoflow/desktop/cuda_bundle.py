"""Build-time CUDA dependency collection for portable ONNX GPU releases."""

import importlib.metadata
from pathlib import Path

from packaging.requirements import Requirement


def cuda_distributions() -> list[str]:
    """Resolve installed NVIDIA libraries required by this exact ONNX GPU wheel.

    CUDA and cuDNN are optional extras in the GPU wheel's metadata. Include their
    NVIDIA dependencies recursively, checking compatibility rather than guessing
    library names or requiring a CUDA toolkit on the destination computer.
    """
    onnxruntime = importlib.import_module("onnxruntime")

    if "CUDAExecutionProvider" not in onnxruntime.get_available_providers():
        return []
    gpu = importlib.metadata.distribution("onnxruntime-gpu")
    pending = []
    for text in gpu.requires or []:
        requirement = Requirement(text)
        marker = requirement.marker
        allowed = marker is None
        if marker is not None:
            allowed = marker.evaluate({"extra": "cuda"}) or marker.evaluate({"extra": "cudnn"})
        if requirement.name.startswith("nvidia-") and allowed:
            pending.append(requirement)
    if not pending:
        raise RuntimeError(
            "The ONNX GPU wheel does not declare CUDA libraries; use a supported wheel"
        )
    included: set[str] = set()
    while pending:
        requirement = pending.pop()
        try:
            distribution = importlib.metadata.distribution(requirement.name)
        except importlib.metadata.PackageNotFoundError as exc:
            raise RuntimeError(
                "CUDA release libraries are missing. Install "
                f"onnxruntime-gpu[cuda,cudnn]=={gpu.version} before packaging."
            ) from exc
        if distribution.version not in requirement.specifier:
            raise RuntimeError(
                f"Incompatible CUDA package: {requirement}, got {distribution.version}"
            )
        if requirement.name in included:
            continue
        included.add(requirement.name)
        for text in distribution.requires or []:
            dependency = Requirement(text)
            if dependency.name.startswith("nvidia-") and (
                dependency.marker is None or dependency.marker.evaluate({"extra": ""})
            ):
                pending.append(dependency)
    return sorted(included)


def cuda_binaries(packages: list[str]) -> list[tuple[str, str]]:
    result = []
    names: dict[str, Path] = {}
    for name in packages:
        distribution = importlib.metadata.distribution(name)
        libraries = []
        for item in distribution.files or []:
            path = Path(str(distribution.locate_file(item)))
            if path.suffix.lower() == ".dll" or ".so" in path.suffixes:
                if not path.is_file():
                    raise RuntimeError(f"CUDA library is missing: {path}")
                existing = names.get(path.name)
                if existing is not None and existing.resolve() != path.resolve():
                    raise RuntimeError(f"Conflicting CUDA libraries named {path.name}")
                names[path.name] = path
                libraries.append((str(path), "cuda"))
        if not libraries:
            raise RuntimeError(f"No native CUDA libraries found in {name}")
        result.extend(libraries)
    return result
