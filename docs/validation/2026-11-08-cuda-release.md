# Portable CUDA release validation — 2026-11-08

Windows x64, RTX 2080, NVIDIA driver 610.47. Video-Flow 0.17.0.

- The status bar reads `appVersion` from the running backend. API tests pass (19), the frontend was rebuilt, and the packaged screenshot displays **Video-Flow 0.17.0**.
- CUDA package collection resolves the ONNX GPU wheel's CUDA/cuDNN NVIDIA dependencies recursively, verifies compatible versions, collects 20 native libraries, and retains all seven NVIDIA distribution metadata/licence directories. Missing libraries fail packaging. CPU builds skip collection.
- PyInstaller staging build succeeded in 424.78 seconds. Fresh-directory component diagnostic exited 0, reported version 0.17.0, and ran CUDA inference successfully with PATH limited to Windows system directories, CUDA_PATH and PYTHONPATH cleared. No model files were present or downloaded. Report: `.cache/cuda-isolated-report.json`.
- Native Qt packaged smoke passed eight checks in 7.30 seconds (native bridge/drop, scoped path import, VP9 playback, Space, linked split, undo, reload). Original unchanged; no original copies; backend stopped. FFmpeg alone was added to the minimal system PATH. Disposable recent-list and cache overrides isolated user state. Report/screenshot: `.cache/cuda-packaged-smoke/`.
- Backend: 517 passed, one optional ONNX authoring test skipped, one existing Windows symlink-permission failure (WinError 1314). New packaging/component/provider tests pass (19 plus one optional skip); CUDA collector tests pass (4). Backend Ruff lint and format checks pass.
- Frontend: 92 tests pass; typecheck and production build pass. Existing repository-wide formatting and typing issues documented in `docs/validation/2026-11-08-components.md` remain; no new typing errors in the CUDA collector.
- Updated only the executable and `_internal/` in `releases/Video-Flow`; existing model file counts/bytes and settings hash are unchanged. Tools and other user-owned sibling folders are preserved.

Linux and other GPUs have not been qualified by this Windows validation. The complete release folder is required; GPU drivers remain system prerequisites.
