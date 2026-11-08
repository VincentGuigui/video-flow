# Release notes

Major changes per version, newest first. Every delivered change set bumps the minor version; the major version changes for breaking changes. The version is set in `backend/pyproject.toml`, `backend/videoflow/__init__.py` and `frontend/package.json`, and recorded in each saved `project.json` (`app.version`).

## 0.22.0 — 2026-11-08

- Set output resolution from Project properties

## 0.21.0 — 2026-11-08

- Correct transcript words in place and persist analysis JSON

## 0.20.0 — 2026-11-08

- Map transcript text selections onto the timeline range

## 0.19.0 — 2026-11-08

- Show transcribed media topics after two seconds of hover

## 0.18.0 — 2026-11-08

- Double-click assembly clips to focus their edit

## 0.17.0 — 2026-11-08

- Fix CUDA failing when a desktop release is moved to a fresh directory: CUDA builds now include compatible NVIDIA runtime libraries and preload the bundled directory.
- Packaging rejects missing or incompatible CUDA libraries and retains NVIDIA licence metadata. A component diagnostic validates actual GPU inference without models or development paths.

## 0.16.0 — 2026-11-08

- The status bar displays the running backend application version instead of a hard-coded label.

## 0.15.0 — 2026-11-08

- Initial component setup detects missing inference dependencies even when model files exist, and offers explicit installation, progress and cancellation in source desktop builds.
- CUDA readiness is checked with actual inference; missing GPU libraries can be installed, or CPU use selected. CUDA libraries are preloaded before model sessions. Incomplete frozen builds report that the release needs reinstalling.
- Keep Whisper optional in desktop installs so its CPU ONNX dependency does not overwrite an installed GPU runtime.

## 0.14.0 — 2026-11-08

- Fix Qwen analysis failing with a missing PyTorch module: desktop installation includes Qwen and Whisper runtimes, and the run scripts restore desktop dependencies removed by a later environment sync.
- Release builds include Qwen and refuse to package missing inference runtimes. Model downloads remain explicit; existing weights are reused.

## 0.13.0 — 2026-11-04

- Hovering a clip in the flow shows a one-line description of it, taken from its analysis; audio clips show the same text as their video.
- Analysing a medium again now refreshes its transcript and tooltips at once.

## 0.12.0 — 2026-11-01

- Faster start: the window opens at once with a loading screen while the local service starts; FFmpeg's capabilities are probed once per build instead of at every launch.
- The log records how long each step of the start took.
- Fix: the desktop app no longer crashes at start on Linux (file drops are watched on the editor only).

## 0.11.0 — 2026-11-01

- Keyframed transforms: animate a video clip's position, size, rotation, crop and opacity from the Animation tab (K adds a keyframe), with smooth or linear interpolation; keyframes are diamonds on the timeline (move, delete). Rendered, and exported to Camtasia.
- Zoom & pan is replaced by keyframes; zooms of earlier projects are ignored (no migration).

## 0.10.0 — 2026-11-01

- Freeze frame (F, or Freeze in the flow toolbar): inserts a 3 s still of the frame at the cursor, splitting the clip and its audio around it; exported as Camtasia image clips, OTIO freeze effects and EDL M2 freezes.

## 0.9.0 — 2026-11-01

- Still images (PNG, JPEG, WebP, BMP, TIFF) in the media library; each becomes a 3 s image clip that trims freely, takes transitions, fades and zoom, renders and exports (Camtasia image clips).

## 0.8.0 — 2026-11-01

- Effects tab in clip properties: transition cards with picture tiles, and one card per clip effect with Add effect and remove.
- Cut markers in the clip flow and transition bands in the timeline open the transition of that cut.

## 0.7.0 — 2026-11-01

- Properties panel: resizable width, half or tall height, pinned or floating (folds into a strip when the pointer leaves, opens again on hover).

## 0.6.0 — 2026-11-01

- Right-click shows only the app's own menus; the browser menu (reload, copy address) is gone.

## 0.5.0 — 2026-11-01

- FFmpeg window: when no FFmpeg 6.1+ is found, the app offers at start (and from Settings) to download a pinned, checksum-verified build into `tools/ffmpeg/`, with its licence files, only on the user's consent.
- The install scripts ask before downloading FFmpeg (`--yes` / `-Yes` to accept), always verify its checksum and keep its licence files; the Linux build moved to a working URL.

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
