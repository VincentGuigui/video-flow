# Release notes

Major feature changes per version. The version is set in `backend/pyproject.toml`, `backend/videoflow/__init__.py` and `frontend/package.json`.

## 0.1.0 — unreleased

- Desktop editor (PySide6 / Qt WebEngine) with native imports that reference originals in place, project home, save and save as.
- Local analysis: transcription (Parakeet TDT or Whisper), summary, keywords and topic sections; models downloaded on request, NPU → GPU → CPU.
- Retakes stacked on import by sentence similarity; compare takes side by side and pick one.
- Editing: layered clip flow, linked video/audio, split, lift, ripple delete, trim modes, undo/redo, timeline range, transcript-driven trimming, auto-trim silence, workspace zones with select all and delete.
- Finishing: transitions (dissolve, dips), fades, speed, zoom & pan, mute ranges, ducking under speech, titles and lower thirds.
- Output: MP4 render with loudness normalisation; OTIO, OTIOZ, EDL, SRT, paper edit, transcript and Camtasia 2023.4+ exports.
