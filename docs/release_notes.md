# Release notes

Major changes per version, newest first. Every delivered change set bumps the minor version; the major version changes for breaking changes. The version is set in `backend/pyproject.toml`, `backend/videoflow/__init__.py` and `frontend/package.json`, and recorded in each saved `project.json` (`app.version`).

## 0.4.0 — 2026-11-01

- GitHub releases for Windows and Linux, built by a workflow from a version tag.
- Re-analysing a medium stacks its clip over the retake it matches.
- SRT and paper edit leave out words said inside mute ranges; the paper edit shows the transcript of editor clips again.

## 0.3.0 — 2026-11-01

- Manage AI models window (from Settings, at first start and when an import needs a model): exact download size before downloading (from the Hub metadata, cached), size on disk, download, update, cancel and remove per model.
- `Add Video-Flow to Start Menu.bat` (Windows) / `add-video-flow-to-menu.sh` (Linux) next to the packaged executable.

## 0.2.0 — 2026-11-01

First numbered version; it gathers everything built so far.

- Desktop editor (PySide6 / Qt WebEngine) with native imports that reference originals in place, project home, save and save as.
- Local analysis: transcription (Parakeet TDT or Whisper), summary, keywords and topic sections; models downloaded on request, NPU → GPU → CPU.
- Retakes stacked on import by sentence similarity; compare takes side by side and pick one.
- Editing: layered clip flow, linked video/audio, split, lift, ripple delete, trim modes, undo/redo, timeline range, transcript-driven trimming, auto-trim silence, workspace zones with select all and delete.
- Finishing: transitions (dissolve, dips), fades, speed, zoom & pan, mute ranges, ducking under speech, titles and lower thirds.
- Projects live in the working folder as `<name>.video-flow`, with media referenced relative to it; recent projects per user on the home page (open, rename, remove from list, delete to the trash); Open accepts only valid project folders; caches kept outside projects and managed in Settings (obsolete in-project caches of older projects are removed on open).
- Project media context menu: Info and Analyse again.
- Output: MP4 render with loudness normalisation; OTIO, OTIOZ, EDL, SRT, paper edit and Camtasia 2023.4+ exports.
