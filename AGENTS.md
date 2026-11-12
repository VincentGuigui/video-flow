# AGENTS.md

## Project

Video-Flow is a local-first desktop app for assembling footage shot with many retakes. It imports rushes, transcribes and analyses them locally, stacks retakes of the same sentences so they can be compared, then lets the user cut, layer and finish the edit (transitions, fades, speed, keyframed transforms, ducking, titles). It renders an MP4 with FFmpeg or exports to OpenTimelineIO, EDL, SRT, paper edit or Camtasia (2023.4+).

Targets Windows and Linux (x64). AI runs on the NPU, then the GPU, then the CPU. Originals are never copied or modified.

## Key elements

- **Stack:** Python 3.13 backend (`backend/`, package `videoflow`, uv, FastAPI) hosted in a PySide6 / Qt WebEngine window; React + Vite + Zustand frontend (`frontend/`, npm). FFmpeg >= 6.1 for media and rendering.
- **Edit model:** the editor document (`backend/videoflow/editor/models.py`, mirrored in `frontend/src/model.ts`) holds clips in integer project-rate frames: video, audio, empty (`gap`) and text clips on numbered lanes, linked video/audio pairs, transitions. Backend and frontend logic mirror each other (transitions, keyframes, volume, titles): change both together.
- **Edits are commands:** the frontend saves the whole document with `SetEditor` through `PATCH /api/project`; every save is one undo step.
- **Render:** `backend/videoflow/render/graph.py` compiles the document into FFmpeg filter graphs; titles are drawn by Pillow (`editor/titles.py`) with the bundled Inter font.
- **Project bundle:** `<name>.video-flow` folder inside the user's working folder (next to the media, referenced by relative paths; `project/library.py`, per-user recent list in `recent-projects.json` under `runtime.user_data_dir()`), with `project.json`, analysis, features, exports and renders. Rebuildable caches (proxies, thumbnails, waveforms, title pictures) live outside it in `cache/<project id>/` beside the application (`runtime.cache_root()`).
- **`tools/` is a fixed name:** the installer puts the static FFmpeg in `tools/ffmpeg/`, and `media/caps.py` and the run scripts look there before `PATH`. It is git-ignored.
- **Sample media are generated, not versioned:** `scripts/gen_samples.py` (code in `backend/videoflow/samples.py`) builds them with FFmpeg and TTS into a per-user cache (`VIDEOFLOW_SAMPLES_CACHE` overrides). Tests make their own synthetic media.
- **Models:** pinned in `backend/videoflow/engines/manifest.toml`, stored in the application `models/` folder, downloaded only on request from Settings.

## Layout

| Path | Content |
|------|---------|
| `backend/` | API, editor model, media, analysis engines, render, exporters, desktop shell, tests |
| `frontend/` | Editor UI; `src/*.ts` pure logic with vitest tests, `src/ui/` React components |
| `assets/` | Bundled resources: `fonts/` (Inter, OFL), `icons/` (app icon, drawn by `scripts/make_icons.py`); found through `runtime.assets_dir()` |
| `.github/workflows/` | `release.yml`: builds and publishes the Windows and Linux releases (tag `v<version>`) |
| `scripts/` | Install, run and dev scripts (`*.sh` Linux, `*.ps1` and `*.bat` Windows), desktop build spec |
| `docs/` | Documentation |

## Documentation

- `README.md`: a snapshot of what is developed (what it does, install, run, usage). Always update and consolidate it with each feature: describe the current state, no history or changelog.
- `docs/roadmap.md`: built / next / later. Update it with each feature.
- `docs/release_notes.md`: changes per version for users, newest first. Every version gets a section `## <version> — <date>` with one line per change: `- <TYPE>: <short, explicit sentence for users>`, `TYPE` being `FEATURE` (new), `IMPROVEMENT` (works better), `FIX` (bug fixed) or `DEV` (infrastructure or technical only). The release workflow rejects any other line. The GitHub release text is built from it with the fixed template `.github/release-notes-template.md` (How to install, then What's new?): every `FEATURE`, `IMPROVEMENT` and `FIX` entry since the previous GitHub release, `DEV` left out (see `docs/reference/github-releases.md`). Change the template, not the workflow, to change the release text.
- `docs/README.md`: index of the documentation. `docs/product/` functional spec (what the product is meant to do; keep its status marks and non-goals true), `docs/features/` the user manual (`docs/features/README.md`: end-to-end workflow and the list of pages, then one page per built feature, current behaviour, in one subfolder per stage: `getting-started/`, `import-analysis/`, `editing/`, `finishing/`, `output/`), `docs/architecture/` how it is built, `docs/decisions/` dated decision records (history, not rewritten), `docs/reference/` dependencies and runtime notes, `docs/validation/` validation records.
- `docs/reference/dependencies.md`: every dependency with version, licence and purpose. Update it with any dependency change.

## Rules

- **Commits:** atomic, one feature or fix per commit, with a concise message prefixed by its type: `FEATURE:`, `FIX:`, `DOC:`, `DEV:` (tooling, tests, build, refactoring). Never add a `Co-Authored-By` or any other trailer mentioning AI co-authoring.
- **Docs:** document every feature in the user manual: a page (or a section of the closest one) in the stage subfolder of `docs/features/`, listed in `docs/features/README.md`, written as instructions for users (technical rules to `docs/architecture/`, tests to `docs/validation/`, linked from a short "Technical notes" section); keep the workflow diagram of that root page true, and update `README.md` and `docs/roadmap.md` in the same change. When a feature is removed or replaced, amend every description of it in `docs/`. Refer to documents by path (e.g. `docs/features/finishing/clip-effects.md`), not by number.
- **Version:** every delivered change set (features or fixes) bumps the minor version (0.2.0 → 0.3.0); the major version changes only for breaking changes (for example a project file older versions cannot open). Update `backend/pyproject.toml`, `backend/videoflow/__init__.py`, `frontend/package.json` (and its lock) together, and add a section to `docs/release_notes.md`. Change only the version fields: never search and replace the version number across files (it altered dependencies of `frontend/package-lock.json` once).
- **Project file:** `project.json` records `schemaVersion` (format) and `app.version` (last saving app). Every structural change to it (renamed, moved or removed field, changed meaning or units, new required data) needs a migration path: bump `SCHEMA_VERSION` (`project/models.py`), add the `vN → vN+1` function to `MIGRATIONS` (`project/migrations.py`) and test it on a file of the previous version. A file from an older version that opens without problem is saved at once as a current-version file.
- No refactoring, rollback, framework or major-version change without asking first.
- Windows and Linux: pathlib, no `shell=True`; every script exists as `.sh` (Linux) and `.ps1` (Windows), with numbered `.bat` wrappers for Windows in usage order (`1-install`, `2-dev`, `3-run`, `4-build`, `5-package`) that run the `.ps1`.
- English everywhere (code, comments, docs, commit messages).

## Checks

```bash
cd backend && uv run pytest && uv run ruff check . && uv run ruff format --check . && uv run mypy
cd frontend && npm test && npm run typecheck && npx prettier --check src
```

Regenerate schema goldens after model changes: `uv run python -m videoflow.project.schema --write`. `uv run pytest -m smoke` runs the model-downloading tier; the unit tier uses synthetic media and no network.
