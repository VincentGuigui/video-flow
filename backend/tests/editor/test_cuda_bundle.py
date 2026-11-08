from types import SimpleNamespace

import pytest

from videoflow.desktop import cuda_bundle
from videoflow.hw import ai


def test_cpu_build_does_not_require_nvidia_packages(monkeypatch):
    import onnxruntime

    monkeypatch.setattr(onnxruntime, "get_available_providers", lambda: ["CPUExecutionProvider"])
    assert cuda_bundle.cuda_distributions() == []


def test_cuda_build_requires_compatible_libraries_and_transitive_dependencies(monkeypatch):
    import onnxruntime

    monkeypatch.setattr(onnxruntime, "get_available_providers", lambda: ["CUDAExecutionProvider"])
    distributions = {
        "onnxruntime-gpu": SimpleNamespace(
            version="1.31.0",
            requires=[
                'nvidia-cuda-runtime~=13.0; extra == "cuda"',
                'nvidia-cudnn-cu13~=9.0; extra == "cudnn"',
                "numpy>=1.21",
            ],
        ),
        "nvidia-cuda-runtime": SimpleNamespace(version="13.5.37", requires=[]),
        "nvidia-cudnn-cu13": SimpleNamespace(
            version="9.28.1.4", requires=["nvidia-cublas>=13,<14"]
        ),
        "nvidia-cublas": SimpleNamespace(version="13.10.0.20", requires=[]),
    }

    def distribution(name):
        if name not in distributions:
            raise cuda_bundle.importlib.metadata.PackageNotFoundError(name)
        return distributions[name]

    monkeypatch.setattr(cuda_bundle.importlib.metadata, "distribution", distribution)
    assert cuda_bundle.cuda_distributions() == [
        "nvidia-cublas",
        "nvidia-cuda-runtime",
        "nvidia-cudnn-cu13",
    ]
    distributions["nvidia-cublas"].version = "12.0"
    with pytest.raises(RuntimeError, match="Incompatible CUDA"):
        cuda_bundle.cuda_distributions()
    del distributions["nvidia-cublas"]
    with pytest.raises(RuntimeError, match="Install onnxruntime-gpu\\[cuda,cudnn\\]==1.31.0"):
        cuda_bundle.cuda_distributions()


def test_cuda_library_collection_preserves_native_files_without_headers(tmp_path, monkeypatch):
    for name in ["cublas64_13.dll", "libcublas.so.13", "header.h"]:
        (tmp_path / name).write_bytes(b"fixture")
    distribution = SimpleNamespace(
        files=["cublas64_13.dll", "libcublas.so.13", "header.h"],
        locate_file=lambda p: tmp_path / p,
    )
    monkeypatch.setattr(cuda_bundle.importlib.metadata, "distribution", lambda name: distribution)
    result = cuda_bundle.cuda_binaries(["nvidia-cublas"])
    assert {path.rsplit("/", 1)[-1].rsplit("\\", 1)[-1] for path, _ in result} == {
        "cublas64_13.dll",
        "libcublas.so.13",
    }
    assert all(destination == "cuda" for _, destination in result)


def test_frozen_runtime_preloads_its_own_cuda_folder(tmp_path, monkeypatch):
    (tmp_path / "cuda").mkdir()
    calls = []
    monkeypatch.setattr(ai.sys, "frozen", True, raising=False)
    monkeypatch.setattr(ai.sys, "_MEIPASS", str(tmp_path), raising=False)
    monkeypatch.setattr(
        ai,
        "_import_ort",
        lambda: SimpleNamespace(preload_dlls=lambda **kwargs: calls.append(kwargs)),
    )
    monkeypatch.setattr(ai.os, "add_dll_directory", lambda p: object(), raising=False)
    monkeypatch.setattr(ai, "_CUDA_DLL_DIRECTORIES", [])
    ai.preload_cuda.cache_clear()
    ai.preload_cuda()
    assert calls == [{"directory": str(tmp_path / "cuda")}]
    ai.preload_cuda.cache_clear()
