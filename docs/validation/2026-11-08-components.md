# Component setup validation — 2026-11-08

Windows x64, NVIDIA GeForce RTX 2080, driver 610.47, Python 3.13.17, ONNX Runtime GPU 1.31.0, PyTorch 2.14.1+cpu.

- Reproduced missing torch in the source environment with Qwen selected. Installed torch/Transformers/safetensors; existing Qwen weights reused, real summary/keywords succeeded.
- Reproduced CUDA startup failure: cublasLt64_13.dll missing. Installed the existing ONNX GPU package's cuda/cudnn extras in the source environment. DLL preloading plus a real ONNX session succeeded.
- Real Parakeet transcription of disposable 9-second speech media returned 30 timecoded words with engine device `gpu`; Qwen produced a summary and five keywords. No original user media was changed.
- Native Qt check with simulated missing torch displayed **Install components**, **Qwen runtime · Missing** and **Install dependencies**; backend shutdown succeeded. Screenshot/report: `.cache/components-popup/`.
- Native baseline smoke passed eight checks (scoped drop/import, VP9 playback, Space, focused linked split, undo, reload, original references), 6.71 seconds; source unchanged, no original copies, backend stopped. Report: `.cache/components-smoke-retry/report.json`.
- Component/settings/provider/ASR regression tests: 35 passed, one optional ONNX authoring test skipped, one existing symlink-permission test deselected. Covers missing dependencies with models present, fixed package whitelist, browser/frozen restrictions, cancellation, single-flight installation, CUDA silent fallback and inference.
- Full backend suite before the component extension: 507 passed, one skipped, one failure caused by missing Windows symlink privileges (WinError 1314). Backend Ruff lint and formatting pass after the component extension.
- Frontend: 92 tests pass, typecheck and production build pass. New RuntimeSetup formatting passes. Existing frontend-wide Prettier check reports 50 previously unformatted files.
- Existing strict typing errors remain in runtime.py (unused Windows ignore), onnx_st.py (tokenizers missing stubs), summary.py (two untyped third-party calls exposed by installing Transformers). No new component typing errors.
- The older extended native smoke timed out in live-properties, which depends on selectors from an earlier UI revision. Baseline playback and the new component popup were validated separately; do not treat the extended check as passing.

No frozen executable was rebuilt in this change. Python dependency installation in frozen builds is intentionally unavailable: incomplete bundled runtimes require reinstalling the release. Linux and other accelerators require their own validation.
