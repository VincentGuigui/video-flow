# Video-Flow

Local-first assembly tool for footage shot with many retakes: ingest rushes, transcribe and analyse them, group equivalent takes into beats, compare alternatives side by side, then render with FFmpeg or export to an editor (OpenTimelineIO, FCPXML, EDL, Camtasia).

Status: implementation in progress. The PySide6/Qt WebEngine desktop editor hosts the React workspace: preview, transport timeline, layered clip flow, linked edits, trim modes, undo/redo, native file-reference imports, progress/cancellation and analysis-sidecar reuse. FastAPI serves the authenticated local API and media. OTIO/OTIOZ, EDL, SRT and paper-edit exports are available. Final-video rendering, full analysis calibration and release hardening remain unfinished.

Targets Windows 11 x64 and Linux x86_64; Windows ARM64 requires qualification. Native desktop development playback has been checked on Windows x64. AI inference runs on NPU, then GPU, then CPU.

## Essentials

- Backend: Python 3.13, FastAPI, managed with [uv](https://docs.astral.sh/uv/) in `backend/` (package `videoflow`).
- Desktop: PySide6 + Qt WebEngine; normal launch opens a native application window.
- Frontend: React + Vite, built with Node >=22.12 and npm. Node is a build-time dependency only.
- Media: FFmpeg >= 6.1 (system or static build in `tools/ffmpeg/`).

## Install

```bash
scripts/install.sh            # Linux
```
```powershell
scripts\install.ps1           # Windows
```

The installer sets up uv, Python 3.13, FFmpeg, checks Node/pnpm, detects the hardware and runs `uv sync` with the desktop extra and matching inference extra (`openvino`, `cuda`, `directml`, `qnn` or `cpu`). Build the interface once with `npm install` then `npm run build` in `frontend/`. Flags: `--cpu-only`, `--extra X` (repeatable, e.g. `--extra whisper`), `--no-ffmpeg`, `--no-frontend-check` (PowerShell: `-CpuOnly`, `-Extra X`, `-NoFfmpeg`, `-NoFrontendCheck`). The accelerator extras are mutually exclusive; see [docs/dependencies.md](docs/dependencies.md).

## Run

```bash
scripts/run.sh                 # native desktop window
scripts/run.sh --help          # any other arguments go to the videoflow CLI
```
(`scripts\run.ps1` on Windows.)

Use `videoflow desktop --project PATH.videoflow` to open/create a particular project. Import uses native dialogs and OS file drops: originals stay in place, and derived proxies, thumbnails and waveforms live in the project bundle. Read-only source folders use bundle-cached analysis. Offline sources can be relinked through a native picker without losing edits. `videoflow serve --project PATH.videoflow` is an explicit browser diagnostic option; normal desktop import never uploads or copies original media.

Keyboard: Space plays the timeline range (start/end markers on the ruler; with a marker selected, 2 s around it); arrows one frame; Shift+arrows one second; Ctrl+arrows ten seconds; Home/End or Ctrl+Shift+arrows timeline bounds; S split; Delete lift with an empty clip; Backspace ripple delete; Escape leave clip focus; Ctrl+Z undo, Ctrl+Shift+Z redo. Ctrl+wheel zooms around the pointer. Double-click a clip to focus it with two seconds of context; top trim handles ripple, bottom handles preserve time with empty clips. Shift stretches scale/crop; Alt edits symmetrically.

See [desktop runtime and platform checks](docs/desktop-runtime.md) and the authoritative [desktop spec](docs/spec/10-desktop-shell.md).

## Develop

```bash
just test | smoke | lint | serve        # or: scripts/dev.sh test | smoke | lint | serve  (scripts\dev.ps1)
```

`test` runs the unit tier (CPU, synthetic media, no network; tests that need the `ml` extra are skipped without it); `smoke` runs the tests marked `smoke` (small CPU models, downloads them; needs an inference extra such as `cpu`/`smoke`, and `whisper` for the faster-whisper test). Synthetic samples are generated with FFmpeg (needs the `flite` filter) and cached under `VIDEOFLOW_SAMPLES_CACHE`.

The standalone desktop build is in `releases/Video-Flow/Video-Flow.exe`. Keep the entire `Video-Flow/` folder together when moving or distributing it. Repository `tools/` is reserved for development dependencies.

## Transcript and topics

Analysed imports get a short summary and topic sections (start/end time and a title of up to five words). Select a clip and open the Transcript tab in the properties panel: click a topic to expand its transcript and set the timeline range to it; click a word (Shift+click to extend) to set the range; click any timecode to move the cursor there. In the Clip tab, Trim clip to range keeps only the range and moves later clips earlier; Auto-trim silence trims to the first and last spoken words.

## Compare takes

Import stacks similar retakes on parallel lanes. Select one and click Compare takes in clip properties: the takes play side by side, synced on their first common word, with words said in only one take highlighted. Pick a take with its button or keys 1–9; it is enabled and the other takes are disabled.

## Settings and local models

Use Settings in the editor header to select transcription and summary engines, manage model downloads and set import/export defaults. Models always live in the application `models/` subdirectory; `VIDEOFLOW_MODELS_DIR` points there. Missing weights require an explicit download action. Compatible analysis JSON is reused first. Deterministic summaries need no generative model; optional Qwen summaries run locally on CPU. Development installs offering both optional engines use `uv sync --extra desktop --extra cpu --extra whisper --extra qwen` in `backend/`.

The logo opens the project library. Save names an untitled project; Save as copies the edit with source references retained. Export → Save as MP4 video renders the enabled edit with progress, cancellation and a native save dialog. Other handoff formats remain available below it.

## Export an edit

From `backend/` after installation:

```powershell
uv run videoflow export C:\Rushes\demo.videoflow --otio --edl --paper-edit
uv run videoflow export C:\Rushes\demo.videoflow --otioz
uv run videoflow export C:\Rushes\demo.videoflow --srt --transcripts words.json
```

The input may also be a `project.json` file. With no format flags, export defaults to OTIO. Files are written to the bundle's `exports/` folder, or `--output DIRECTORY`. Use `--overwrite` to replace existing exports. Each run produces `edit.report.json` with resolver warnings and format limitations. `--include-alternates` adds disabled alternate-take tracks to OTIO/OTIOZ.

SRT takes a JSON object mapping asset IDs to transcript objects, for example:

```json
{"ast_example": {"words": [{"text": "Bonjour.", "startUs": 1200000, "endUs": 1800000}]}}
```

Word times refer to the original source. Subtitles follow the audible cut, including replacement audio and transcript corrections; fillers are removed. Cues stay within clip boundaries, have up to two 42-character lines, and extend to one second when space permits. Transcript corrections lack word timings and are distributed within their authored range. Paper edits can be exported without transcripts.

OTIO retains exact transition definitions, editing identifiers and clip settings as Video-Flow metadata. Other editors may ignore gain, fades, fit and freeze handles. OTIOZ copies source media and requires every referenced file to exist. EDL contains V1 only, uses eight-character reels with a mapping file, and approximates other transitions as dissolves. FCPXML remains planned for P1; real-editor interoperability is not yet validated.

## Documentation

- [Specification](docs/spec/README.md), with authoritative [desktop architecture](docs/spec/10-desktop-shell.md) and [editor/settings refinements](docs/spec/11-editor-refinements.md)
- [Dependencies and accelerator matrix](docs/dependencies.md)
- [Agent guidelines](AGENTS.md): docs location, commit and spec rules
