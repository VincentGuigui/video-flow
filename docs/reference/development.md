# Development: install from source, run, test, package

For using the app, download a release instead ([README](../../README.md#install)). This page is for working on Video-Flow itself.

## Stack

- Backend: Python 3.13, FastAPI, managed with [uv](https://docs.astral.sh/uv/) in `backend/` (package `videoflow`).
- Desktop: PySide6 + Qt WebEngine; a normal launch opens a native window hosting the editor.
- Frontend: React + Vite + Zustand in `frontend/`, built with Node >= 22.12 and npm. Node is a build-time dependency only.
- Media: FFmpeg >= 6.1 (system, or a pinned static build in `tools/ffmpeg/`, see [FFmpeg setup](../features/getting-started/ffmpeg-setup.md)).
- AI: ONNX Runtime (with the execution provider of your hardware), optional PyTorch/Transformers for Qwen summaries and faster-whisper; see [dependencies](dependencies.md).

## Install

```bash
scripts/install.sh            # Linux
```
```powershell
scripts\1-install.bat         # Windows (or install.ps1 from PowerShell)
```

The installer sets up uv, Python 3.13 and FFmpeg (it asks before downloading a pinned, checksum-verified GPL build when none is installed), checks Node, detects the hardware and runs `uv sync` with the desktop extra and the matching inference extra (`openvino`, `cuda`, `directml`, `qnn` or `cpu`; they are mutually exclusive). Build the interface once with `npm install` then `npm run build` in `frontend/`.

Flags: `--cpu-only`, `--extra X` (repeatable, e.g. `--extra whisper`), `--yes` (accept the FFmpeg download), `--no-ffmpeg`, `--no-frontend-check` (PowerShell: `-CpuOnly`, `-Extra X`, `-Yes`, `-NoFfmpeg`, `-NoFrontendCheck`). Without FFmpeg, the app offers to download it at start. The desktop extra includes the Qwen (PyTorch/Transformers) runtime; model weights are downloaded only on request. The Install components window checks missing inference dependencies and validates CUDA with a real inference, offering installation in source builds or CPU use. A development install offering both optional engines: `uv sync --extra desktop --extra cpu --extra whisper --extra qwen` in `backend/`.

## Run

```bash
scripts/run.sh                 # native desktop window
scripts/run.sh --help          # any other arguments go to the videoflow CLI
```

`scripts\3-run.bat` or `scripts\run.ps1` on Windows; double-clicking `3-run.bat` opens the app. The window opens at once with a loading screen while the local service starts; each launch logs how long its steps took (`logs/desktop.log` for the packaged app, the terminal otherwise). `videoflow desktop --project PATH.video-flow` opens or creates a given project; `videoflow serve --project PATH.video-flow` is a browser diagnostic mode. The [command line](command-line.md) also exports projects without the window.

See [desktop runtime and platform checks](desktop-runtime.md) and the [desktop shell](../architecture/desktop-shell.md).

## Develop

```bash
just test | smoke | lint | serve | build | package   # or scripts/dev.sh … (scripts\2-dev.bat or dev.ps1 on Windows)
```

- `test` runs the unit tier (CPU, synthetic media, no network; tests that need the `ml` extra are skipped without it).
- `smoke` runs the tests marked `smoke` (small CPU models, downloads them; needs an inference extra such as `cpu`/`smoke`, and `whisper` for the faster-whisper test). Synthetic samples are generated with FFmpeg (needs the `flite` filter) and cached under `VIDEOFLOW_SAMPLES_CACHE`.
- `build` (`scripts\4-build.bat`) rebuilds the editor interface (`frontend/dist`): run it after pulling frontend changes, since `scripts/run.*` serves the built files.
- `package` (`scripts\5-package.bat`) builds the interface, then the standalone desktop app with PyInstaller into `releases/Video-Flow/`. It replaces only the application files (the executable and `_internal/`), so the models, FFmpeg and settings beside the executable are kept. When no Python code or package changed, it only updates the interface in seconds (`--full` forces a complete rebuild).

The checks run before every commit are listed in [AGENTS.md](../../AGENTS.md#checks); conventions (commits, versions, documentation) are there too.

## Releases

GitHub **Actions → Release → Run workflow** builds the Windows and Linux ZIPs, tags the built commit and publishes the release with SHA-256 checksums; its text lists the changes since the previous release, from [release notes](../release_notes.md). See [automated releases](github-releases.md). Installed apps find new releases themselves ([updates](../features/getting-started/updates.md)).

Next to the executable, `Add Video-Flow to Start Menu.bat` (Windows) or `add-video-flow-to-menu.sh` (Linux) adds a shortcut with the Video-Flow icon to the menu of the current user; run it again after moving the folder. Keep the whole `Video-Flow/` folder together. Repository `tools/` is reserved for development dependencies.
