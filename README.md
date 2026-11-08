# Video-Flow

Local-first desktop app for footage shot with many retakes: import rushes, transcribe and analyse them locally, stack retakes of the same sentences and compare them, cut and finish the edit, then render an MP4 with FFmpeg or export to another editor (OpenTimelineIO, EDL, Camtasia).

Status: the editor, analysis, MP4 render and exports work end to end. Accuracy tuning on real rushes, hardware qualification and release packaging remain; see the [roadmap](docs/roadmap.md).

Targets Windows 11 x64 and Linux x86_64; Windows ARM64 requires qualification. Native desktop development playback has been checked on Windows x64. AI inference runs on NPU, then GPU, then CPU.

## Essentials

- Backend: Python 3.13, FastAPI, managed with [uv](https://docs.astral.sh/uv/) in `backend/` (package `videoflow`).
- Desktop: PySide6 + Qt WebEngine; normal launch opens a native application window.
- Frontend: React + Vite, built with Node >=22.12 and npm. Node is a build-time dependency only.
- Media: FFmpeg >= 6.1 (system, or a pinned static build in `tools/ffmpeg/` downloaded on request by the installer or the app; see [FFmpeg setup](docs/features/ffmpeg-setup.md)).

## Install

```bash
scripts/install.sh            # Linux
```
```powershell
scripts\1-install.bat         # Windows (or install.ps1 from PowerShell)
```

The installer sets up uv, Python 3.13, FFmpeg (it asks before downloading a pinned, checksum-verified GPL build when none is installed), checks Node/pnpm, detects the hardware and runs `uv sync` with the desktop extra and matching inference extra (`openvino`, `cuda`, `directml`, `qnn` or `cpu`). Build the interface once with `npm install` then `npm run build` in `frontend/`. Flags: `--cpu-only`, `--extra X` (repeatable, e.g. `--extra whisper`), `--yes` (accept the FFmpeg download), `--no-ffmpeg`, `--no-frontend-check` (PowerShell: `-CpuOnly`, `-Extra X`, `-Yes`, `-NoFfmpeg`, `-NoFrontendCheck`). Without FFmpeg, the app offers to download it at start. The desktop extra includes the Qwen (PyTorch/Transformers) runtime; model weights are still downloaded only on request in Settings. The initial Install components popup also checks missing inference dependencies and validates CUDA with real inference, offering installation in source builds or CPU use. Packaged Python runtimes are repaired by reinstalling the release. Existing source environments show missing inference dependencies in component setup before analysis. The accelerator extras are mutually exclusive; see [docs/reference/dependencies.md](docs/reference/dependencies.md).

The status bar displays the running backend application version. CUDA desktop builds include compatible NVIDIA runtime libraries; a supported GPU driver remains a system prerequisite.

## Run

```bash
scripts/run.sh                 # native desktop window
scripts/run.sh --help          # any other arguments go to the videoflow CLI
```
(`scripts\3-run.bat` or `scripts\run.ps1` on Windows; double-clicking `3-run.bat` opens the app.) The window opens at once with a loading screen while the local service starts; each launch logs how long its steps took (`logs/desktop.log` for the packaged app, the terminal otherwise).

Projects live in your working folder, next to your media: `<name>.video-flow` with media referenced by relative paths, so the whole folder can be moved or copied. Use `videoflow desktop --project PATH.video-flow` to open/create a particular project. Import uses native dialogs and OS file drops: originals stay in place, and derived proxies, thumbnails and waveforms live in the project bundle. Read-only source folders use bundle-cached analysis. Offline sources can be relinked through a native picker without losing edits. `videoflow serve --project PATH.videoflow` is an explicit browser diagnostic option; normal desktop import never uploads or copies original media.

Keyboard: Space plays the timeline range (start/end markers on the ruler; with a marker selected, 2 s around it); arrows one frame; Shift+arrows one second; Ctrl+arrows ten seconds; Home/End or Ctrl+Shift+arrows timeline bounds; S split; F freeze frame; K keyframe at the cursor; Delete lift with an empty clip; Backspace ripple delete; Ctrl+A select all in the clicked zone; Escape leave clip focus; Ctrl+Z undo, Ctrl+Shift+Z redo. Ctrl+wheel zooms around the pointer. Double-click a clip to focus it with two seconds of context; top trim handles ripple, bottom handles preserve time with empty clips. Shift stretches scale/crop; Alt edits symmetrically.

See [desktop runtime and platform checks](docs/reference/desktop-runtime.md) and the authoritative [desktop spec](docs/architecture/desktop-shell.md).

## Develop

```bash
just test | smoke | lint | serve | build | package   # or scripts/dev.sh … (scripts\2-dev.bat or dev.ps1 on Windows)
```

`test` runs the unit tier (CPU, synthetic media, no network; tests that need the `ml` extra are skipped without it); `smoke` runs the tests marked `smoke` (small CPU models, downloads them; needs an inference extra such as `cpu`/`smoke`, and `whisper` for the faster-whisper test). Synthetic samples are generated with FFmpeg (needs the `flite` filter) and cached under `VIDEOFLOW_SAMPLES_CACHE`.

`build` (`scripts\4-build.bat`) rebuilds the editor interface (`frontend/dist`): run it after pulling frontend changes, since `scripts/run.*` serves the built files. `package` (`scripts\5-package.bat`) builds the interface, then the standalone desktop app with PyInstaller (only needed to distribute the app or to run it without the source tree); it replaces only the application files, so the models, FFmpeg and settings beside the executable are kept. When no Python code or package changed, it only updates the interface in seconds (`--full` forces a complete rebuild). Next to the executable, `Add Video-Flow to Start Menu.bat` (Windows) or `add-video-flow-to-menu.sh` (Linux) adds a shortcut with the Video-Flow icon to the menu of the current user; run it again after moving the folder. GitHub releases for Windows and Linux are built by `.github/workflows/release.yml` when a tag `v<version>` is pushed (or from the Actions tab); see [desktop runtime](docs/reference/desktop-runtime.md). The standalone desktop build is in `releases/Video-Flow/Video-Flow.exe`. Keep the entire `Video-Flow/` folder together when moving or distributing it. Repository `tools/` is reserved for development dependencies.

## Features

- **Transcript and topics:** analysed imports get a summary and titled topic sections. The Transcript tab expands a topic to its lines; clicking a topic or words (Shift+click to extend) sets the timeline range, clicking a timecode moves the cursor.
- **Trim from the range:** Trim clip to range keeps only the range, Delete range cuts it out (later clips move earlier); Auto-trim silence trims to the first and last spoken words.
- **Compare takes:** retakes are stacked on parallel lanes on import (MiniLM sentence similarity plus word overlap). Compare takes plays them side by side, synced on their first common word, with differing words highlighted; pick one with its button or keys 1–9.
- **Transitions:** click the marker on a cut in the clip flow (or a transition in the timeline) to open the Effects tab on that cut, then pick Cut, Cross dissolve, Dip to black or Dip to white and its duration; or apply it to all cuts. Dissolves use media beyond the cut and are shortened (with a warning) when there is not enough.
- **Clip effects:** cards in the Effects tab, added with Add effect and removed with their ×: fade in/out (picture and sound); speed 25–400 % or fit to the range, audio keeping its pitch; mute a range; duck music (an audio clip not linked to a video) by 15 dB under transcribed speech.
- **Titles:** Title and Lower third in the clip flow toolbar add a text clip at the cursor, above the picture; edit text, style, size, colours and box in clip properties.
- **Media menu:** right-click (only the app's menus open, never the browser menu) a medium in Project media for Info (size, duration, location shown in the file manager, analysis and transcript) or Analysis… (transcribe again and replace its analysis).
- **Keyframes:** animate a video clip's position, size, rotation, crop and opacity in the Animation tab (K adds a keyframe at the cursor); values are interpolated (smooth or linear), keyframes show as diamonds on the timeline where they can be moved or deleted.
- **Still images and freeze frames:** import PNG, JPEG, WebP, BMP or TIFF pictures; each becomes a 3 s image clip that you can extend or shorten freely, with transitions, fades and keyframes like a video clip. Freeze (F) inserts a 3 s still of the frame at the cursor, splitting the video clip around it (before it on its first frame, after it on its last).
- **Clip tooltip:** hover a clip in the flow for a one-line description from its analysis (the audio of a video shows the same text as the video).
- **Properties panel:** drag its left edge to resize it; switch it between half height (beside the preview) and tall (beside preview, timeline and flow); unpin it to float over the editor and fold into a strip when the pointer leaves.
- **Zones:** Ctrl+A selects everything in the zone last clicked (project media, timeline, clip flow or editor); Delete removes it. Removing media also removes its clips; undo restores both.

Everything plays in the preview, renders in the MP4 and is exported to Camtasia; the [feature documents](docs/README.md#features) give the details.

## Settings and local models

Use Settings in the editor header to select transcription and summary engines, open Manage AI models (download size, size on disk, download, update, remove), set import/export defaults, and see, open or clear the cache (proxies, thumbnails and waveforms of every project, kept outside the projects and rebuilt when needed). Models always live in the application `models/` subdirectory; `VIDEOFLOW_MODELS_DIR` points there. Missing weights require an explicit download action. Compatible analysis JSON is reused first. Deterministic summaries need no generative model; optional Qwen summaries run locally on CPU. Development installs offering both optional engines use `uv sync --extra desktop --extra cpu --extra whisper --extra qwen` in `backend/`.

The logo closes the current project and opens the home page: recent projects (open, rename, remove from list, delete to the trash), New project (name and working folder) and Open project…. Save names an untitled project; Save as copies the edit with source references retained and opens the copy. The window title shows the open project, and the app reopens the last saved project at launch. Export → Save as MP4 video renders the enabled edit with progress, cancellation and a native save dialog. Other handoff formats remain available below it.

## Export an edit

From `backend/` after installation:

```powershell
uv run videoflow export C:\Rushes\demo.video-flow --otio --edl --paper-edit
uv run videoflow export C:\Rushes\demo.video-flow --otioz
uv run videoflow export C:\Rushes\demo.video-flow --srt --transcripts words.json
```

The input may also be a `project.json` file. With no format flags, export defaults to OTIO. Files are written to the bundle's `exports/` folder, or `--output DIRECTORY`. Use `--overwrite` to replace existing exports. Each run produces `edit.report.json` with resolver warnings and format limitations. `--include-alternates` adds a disabled track to OTIO/OTIOZ for every disabled video clip (an unpicked take), at its position.

SRT takes a JSON object mapping asset IDs to transcript objects, for example:

```json
{"ast_example": {"words": [{"text": "Bonjour.", "startUs": 1200000, "endUs": 1800000}]}}
```

Word times refer to the original source. Subtitles follow the audible cut, including replacement audio and transcript corrections; fillers are removed. Cues stay within clip boundaries, have up to two 42-character lines, and extend to one second when space permits. Transcript corrections lack word timings and are distributed within their authored range. Paper edits can be exported without transcripts.

OTIO retains exact transition definitions, editing identifiers and clip settings as Video-Flow metadata. Other editors may ignore gain, fades, fit and freeze handles. OTIOZ copies source media and requires every referenced file to exist. EDL contains V1 only, uses eight-character reels with a mapping file, and approximates other transitions as dissolves. FCPXML is planned; real-editor interoperability is not yet validated.


Camtasia: Export → Camtasia project, or `uv run videoflow export BUNDLE --camtasia`. To match your Camtasia version exactly, copy any project saved by it to `templates/camtasia.tscproj` in the application folder (or pass `--camtasia-template PATH`); its structures are cloned, its content is not. Crop, backgrounds and transition audio crossfades are not exported (see the export report).

## Documentation

- [Documentation index](docs/README.md): product, features, architecture, decisions, reference
- [Roadmap](docs/roadmap.md): what is built and what comes next
- [Release notes](docs/release_notes.md): major changes per version
- [Dependencies and accelerator matrix](docs/reference/dependencies.md)
- [Agent guidelines](AGENTS.md): conventions for contributors and coding agents

## Editor interactions

- Double-click assembly clips to focus their edit

- Show transcribed media topics after two seconds of hover

- Map transcript text selections onto the timeline range

- Correct transcript words in place and persist analysis JSON

- Set output resolution from Project properties

- Place playback controls above the video preview

- Place clip actions and clip count below the flow

- Merge timeline and clip flow with continuous cursor and range guides

- Delete or ripple the selected range before falling back to whole clips

- Move range trimming and silence trimming into the flow toolbar

- Remove the redundant Delete range action from clip properties

- Show Compare takes in the flow toolbar for parallel takes

- Render a held-edge dissolve when source handles are exhausted

- Preserve transcript corrections when source folders are read-only

Editor interactions:

- Align range guides across the merged timeline workspace
