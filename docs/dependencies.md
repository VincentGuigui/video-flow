# Dependencies

Source of truth for versions: `backend/pyproject.toml` and `backend/uv.lock`. Versions below are those resolved in the lock on 2026-10-23 (minimum constraints in `pyproject.toml`). Every WP that adds a dependency adds a row here (version, licence, purpose).

## Runtime (backend, always installed)

| Package | Version | Licence | Purpose |
|---|---|---|---|
| fastapi | 0.162 | MIT | HTTP API, SSE (`fastapi.sse`), OpenAPI |
| uvicorn[standard] | 0.54 | BSD-3-Clause | ASGI server |
| pydantic | 2.14 | MIT | Project schema, API models, JSON Schema export |
| typer | 0.27 | MIT | `videoflow` CLI |
| numpy | 2.5 | BSD-3-Clause | Audio/embedding arrays |
| scipy | 1.18 | BSD-3-Clause | Signal processing (GCC-PHAT), clustering |
| opentimelineio | 0.18 | Apache-2.0 | Timeline model and OTIO/OTIOZ export |
| OpenTimelineIO-Plugins | 0.18 | Apache-2.0 | Adapters (EDL, FCP XML, ...) |
| rapidfuzz | 3.14 | MIT | Fuzzy text matching for retake detection |
| python-ulid | 4.0 | MIT | Short sortable ids |

## Dev (dependency group `dev`, installed by default by `uv sync`)

| Package | Version | Licence | Purpose |
|---|---|---|---|
| pytest | 9.1 | MIT | Test runner |
| pytest-asyncio | 1.x | Apache-2.0 | Async tests |
| hypothesis | 6.170 | MPL-2.0 | Property tests |
| httpx | 0.28 | BSD-3-Clause | API test client |
| ruff | 0.17 | MIT | Lint and format |
| mypy | 2.4 | MIT | Type checking |

## Optional extras

`ml` (model tooling, no inference runtime; pulled in by every accelerator extra):

| Package | Licence | Purpose |
|---|---|---|
| onnx-asr | MIT | ONNX ASR (Parakeet, Whisper ONNX) |
| scenedetect | BSD-3-Clause | Shot detection |
| opencv-python-headless | Apache-2.0 | Frame decoding, histograms |
| imagehash | BSD-2-Clause | Perceptual hashes |
| huggingface_hub | Apache-2.0 | Model download with pinned revisions |
| tokenizers | Apache-2.0 | Tokenisation for ONNX text models |

The Silero VAD ONNX file is run directly through ONNX Runtime (no `silero-vad` or torch dependency).

Inference runtime (**mutually exclusive**, declared as `conflicts` in `[tool.uv]`: install exactly one per environment, because the `onnxruntime*` wheels overwrite each other):

| Extra | Packages | Licence | Platforms |
|---|---|---|---|
| `smoke` / `cpu` | onnxruntime | MIT | all (same content; `smoke` is the name used by the CI tier) |
| `openvino` | openvino, onnxruntime-openvino | Apache-2.0 / MIT | Windows x64, Linux x64 |
| `cuda` | onnxruntime-gpu | MIT | Windows x64, Linux x64 (needs NVIDIA driver, CUDA 12 and cuDNN) |
| `directml` | onnxruntime-directml | MIT | Windows (any DirectX 12 GPU) |
| `qnn` | onnxruntime-qnn | MIT | Windows ARM64 (Snapdragon X). Python 3.13 wheel availability to verify (H23) |

Combinable with any of the above:

| Extra | Packages | Licence | Purpose |
|---|---|---|---|
| `whisper` | faster-whisper (CTranslate2) | MIT | CPU/CUDA alternative ASR engine, no NPU path |

Example: `uv sync --extra openvino --extra whisper`.

## Accelerator matrix (NPU, then GPU, then CPU)

| OS / hardware | NPU | GPU | CPU | Install extra |
|---|---|---|---|---|
| Windows x64, Intel Core Ultra | OpenVINO (NPU device) | OpenVINO GPU, DirectML | ORT CPU | `openvino` |
| Windows x64, AMD Ryzen AI | ORT VitisAI EP (Ryzen AI SDK, manual) | DirectML | ORT CPU | `directml` (+ SDK) |
| Windows ARM64, Snapdragon X | ORT QNN EP | DirectML (Adreno) | ORT CPU | `qnn` |
| Windows x64, NVIDIA | n/a | CUDA EP (or DirectML) | ORT CPU | `cuda` |
| Windows x64, other GPU | n/a | DirectML | ORT CPU | `directml` |
| Linux x64, Intel Core Ultra | OpenVINO (NPU, `intel_vpu` driver) | OpenVINO GPU | ORT CPU | `openvino` |
| Linux x64, NVIDIA | n/a | CUDA EP | ORT CPU | `cuda` |
| Linux x64, AMD / other | n/a (XDNA not supported by the Python stack here) | ROCm/MIGraphX (best effort, manual) | ORT CPU | `cpu` |

AMD Ryzen AI: the VitisAI execution provider ships with the Ryzen AI SDK (not on PyPI). Install the SDK from AMD, then use its onnxruntime build in a separate environment; `install.ps1` only warns when it detects the NPU. Until then the DirectML or CPU path is used.

FFmpeg hardware paths (separate from the Python extras, probed at run time): decode NVDEC, QSV, VAAPI, D3D11VA; encode `*_nvenc`, `*_qsv`, `*_vaapi`, `*_amf`, `h264_mf`, with libx264/libx265 as fallback.

## External tools

| Tool | Version | Licence | Purpose | Provisioning |
|---|---|---|---|---|
| FFmpeg / ffprobe | >= 6.1 | LGPL/GPL depending on build | Probe, proxies, render | System package, or pinned static build into `tools/ffmpeg/` (`scripts/install.*`). Override with `VIDEOFLOW_FFMPEG_URL` and `VIDEOFLOW_FFMPEG_SHA256` |
| uv | >= 0.5 | MIT / Apache-2.0 | Python and environment manager | Installed by `scripts/install.*` |
| Python | 3.13 | PSF | Backend | `uv python install 3.13` |
| Node.js | 22 | MIT | Frontend build only | Manual (checked by the installer) |
| pnpm | 9+ | MIT | Frontend build only | Manual or `corepack enable pnpm` |
| just | any | CC0 | Optional task runner | Optional; `scripts/dev.{sh,ps1}` are equivalents |
