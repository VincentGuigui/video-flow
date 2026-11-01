# AGENTS.md

## Project

Video-Flow is a local-first desktop app for assembling footage shot with many retakes. It imports rushes, transcribes and analyses them locally, stacks retakes of the same sentences so they can be compared, then lets the user cut, layer and finish the edit (transitions, fades, speed, zoom, ducking, titles). It renders an MP4 with FFmpeg or exports to OpenTimelineIO, EDL, SRT, paper edit or Camtasia (2023.4+).

Targets Windows and Linux (x64). AI runs on the NPU, then the GPU, then the CPU. Originals are never copied or modified.

## Key elements

- **Stack:** Python 3.13 backend (`backend/`, package `videoflow`, uv, FastAPI) hosted in a PySide6 / Qt WebEngine window; React + Vite + Zustand frontend (`frontend/`, npm). FFmpeg >= 6.1 for media and rendering.
- **Edit model:** the editor document (`backend/videoflow/editor/models.py`, mirrored in `frontend/src/model.ts`) holds clips in integer project-rate frames: video, audio, empty (`gap`) and text clips on numbered lanes, linked video/audio pairs, transitions. Backend and frontend logic mirror each other (transitions, zoom, volume, titles): change both together.
- **Edits are commands:** the frontend saves the whole document with `SetEditor` through `PATCH /api/project`; every save is one undo step.
- **Render:** `backend/videoflow/render/graph.py` compiles the document into FFmpeg filter graphs; titles are drawn by Pillow (`editor/titles.py`) with the bundled Inter font.
- **Project bundle:** `*.videoflow` folder with `project.json`, analysis, features, `cache/` (proxies, thumbnails, waveforms, title pictures), exports and renders.
- **`tools/` is a fixed name:** the installer puts the static FFmpeg in `tools/ffmpeg/`, and `media/caps.py` and the run scripts look there before `PATH`. It is git-ignored.
- **Sample media are generated, not versioned:** `scripts/gen_samples.py` (code in `backend/videoflow/samples.py`) builds them with FFmpeg and TTS into a per-user cache (`VIDEOFLOW_SAMPLES_CACHE` overrides). Tests make their own synthetic media.
- **Models:** pinned in `backend/videoflow/engines/manifest.toml`, stored in the application `models/` folder, downloaded only on request from Settings.

## Layout

| Path | Content |
|------|---------|
| `backend/` | API, editor model, media, analysis engines, render, exporters, desktop shell, tests |
| `frontend/` | Editor UI; `src/*.ts` pure logic with vitest tests, `src/ui/` React components |
| `scripts/` | Install, run and dev scripts (`*.sh` Linux, `*.ps1` and `*.bat` Windows), desktop build spec |
| `docs/` | Documentation |

## Documentation

- `README.md`: a snapshot of what is developed (what it does, install, run, usage). Always update and consolidate it with each feature: describe the current state, no history or changelog.
- `docs/roadmap.md`: built / next / later. Update it with each feature.
- `docs/release_notes.md`: major feature changes per version. Add an entry for every major feature change.
- `docs/README.md`: index of the documentation. `docs/product/` functional spec, `docs/features/` one document per built feature (current behaviour), `docs/architecture/` how it is built, `docs/decisions/` dated decision records (history, not rewritten), `docs/reference/` dependencies and runtime notes, `docs/validation/` validation records.
- `docs/reference/dependencies.md`: every dependency with version, licence and purpose. Update it with any dependency change.

## Rules

- **Commits:** atomic, one feature or fix per commit, with a concise message prefixed by its type: `FEATURE:`, `FIX:`, `DOC:`, `DEV:` (tooling, tests, build, refactoring). Never add a `Co-Authored-By` or any other trailer mentioning AI co-authoring.
- **Docs:** document every feature in `docs/features/` (new document or section, listed in `docs/README.md`), and update `README.md` and `docs/roadmap.md` in the same change. When a feature is removed or replaced, amend every description of it in `docs/`. Refer to documents by path (e.g. `docs/features/clip-effects.md`), not by number.
- **Version:** bump the app version when a release-worthy change lands (minor for features, patch for fixes), in `backend/pyproject.toml`, `backend/videoflow/__init__.py` and `frontend/package.json` together, and give it a section in `docs/release_notes.md`.
- No refactoring, rollback, framework or major-version change without asking first.
- Windows and Linux: pathlib, no `shell=True`; every script exists as `.sh` (Linux), `.ps1` (Windows) and a `.bat` wrapper that runs the `.ps1`.
- English everywhere (code, comments, docs, commit messages).

## Checks

```bash
cd backend && uv run pytest && uv run ruff check . && uv run ruff format --check . && uv run mypy
cd frontend && npm test && npm run typecheck && npx prettier --check src
```

Regenerate schema goldens after model changes: `uv run python -m videoflow.project.schema --write`. `uv run pytest -m smoke` runs the model-downloading tier; the unit tier uses synthetic media and no network.
