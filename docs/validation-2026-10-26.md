# Desktop and AI validation — 2026-10-26

Validated on Windows x64, Python 3.13 and PySide6 6.12. Linux and Windows ARM64 remain unqualified.

- Backend suite: 419 passed, one optional ONNX test skipped, ten download-dependent tests deselected. An additional frozen-worker logging regression test passed after the packaged download check exposed a missing console-stream failure.
- Frontend: 21 tests passed; TypeScript and production Vite build passed. Regression coverage includes reversible resolution changes, same-ratio fit/fill toggling, and clearing selection/history when the active project changes.
- Real engines: three Silero/Whisper smoke tests passed. Real downloads of Silero, Whisper tiny and Qwen completed into application-local `models/`; Qwen produced a summary and keywords on CPU.
- Real Qt window: native scoped drop, unchanged originals, no original copies, actual playback, Space, focused linked split, undo, reload, page zoom, project home, blurred preview, validated MP4 and Save as all passed.
- Standalone package: the same editor checks passed. A separate packaged check downloaded Silero through the frozen worker, transcribed generated speech with Whisper, summarized it with Qwen and copied the project with its analysis. The check completed in 71.31 seconds and confirmed owned-backend shutdown. This is a synthetic-fixture check, not a real-rush accuracy or performance benchmark.

The current local executable is `tools/release/Video-Flow/Video-Flow.exe`. Models are not tracked in Git. The local validation installation retains its downloaded model cache; another installation asks before downloading missing models. Test engine preferences were removed after validation.

Build into a fresh staging directory when an existing installation contains `models/` or `settings.json`; PyInstaller's `--noconfirm` replaces its output directory. Preserve those application-owned files when updating an installation. FFmpeg remains separately provisioned beside the executable.

MP4 validation covers integer and NTSC frame counts, layer ordering, crop/position, explicit black/silent clips, enabled state, audio-only edits, normalization, offline failures, cancellation and all three clip-background modes. H.264 MP4 flattens transparent areas over underlying video or black. Legacy transition/fade rendering fails explicitly rather than silently omitting effects.
