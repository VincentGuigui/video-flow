# Editor evolutions validation — 2026-11-08

Each requested evolution was committed separately and pushed. Source application version: 0.32.0. The interface was rebuilt for scripts/3-run.bat; the packaged release remains 0.17.0 and was not rebuilt for this editor change set.

- Frontend: 93 tests pass; typecheck and Vite build pass. Range regression verifies linked-media lift preserves total duration and later starts while ripple closes the selected span.
- Backend: 519 tests pass, one optional ONNX authoring test skipped, one existing Windows symlink privilege failure remains (WinError 1314). Ruff lint and formatting pass. The same four pre-existing strict typing errors remain in runtime.py, summary.py and onnx_st.py.
- Eighteen transition/render tests pass, including a new full-length red-to-blue dissolve test that checks both colors at the midpoint and exact output frame count. The renderer normalizes timestamps after frame padding.
- Transcript correction regression verifies timecodes and original media remain unchanged, cached corrections survive read-only source folders, and stale expected text is rejected.
- Native Qt smoke: eight checks pass in 7.32 seconds (scoped native import, actual decoding and Space playback, focused linked split, undo, reload). Source unchanged, no original copies, backend stopped. Recent-project and cache overrides isolate user state.
- Native screenshot inspected: centered preview playback controls, merged timeline/flow with continuous range and cursor guides, lower flow toolbar, and actual version in status bar. Report/screenshot: .cache/editor-evolutions-smoke/.
- Repository-wide Prettier still reports the previously unformatted files. The new media-topic component is formatted. Dependency versions were checked against the starting lock; no dependency upgrades are part of these editor changes.
