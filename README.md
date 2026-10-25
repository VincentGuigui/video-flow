# Video-Flow

Local-first assembly tool for footage shot with many retakes: ingest rushes, transcribe and analyse them, group equivalent takes into beats, compare alternatives side by side, then render with FFmpeg or export to an editor (OpenTimelineIO, FCPXML, EDL, Camtasia).

Status: implementation in progress. Backend contracts, media services, timeline resolution, jobs, analysis algorithms and AI engines are in place. OTIO/OTIOZ, EDL, SRT and paper-edit exports are available through the CLI. Pipeline orchestration, render, HTTP API and frontend remain to be implemented.

Targets Windows 11 (x64, ARM64) and Linux (x86_64). AI inference runs on NPU, then GPU, then CPU.

## Essentials

- Backend: Python 3.13, FastAPI, managed with [uv](https://docs.astral.sh/uv/) in `backend/` (package `videoflow`).
- Frontend: React + Vite (Node 22, pnpm), added in later work packages.
- Media: FFmpeg >= 6.1 (system or static build in `tools/ffmpeg/`).

## Install

```bash
scripts/install.sh            # Linux
```
```powershell
scripts\install.ps1           # Windows
```

The installer sets up uv, Python 3.13, FFmpeg, checks Node/pnpm, detects the hardware and runs `uv sync` with the matching extra (`openvino`, `cuda`, `directml`, `qnn` or `cpu`). Flags: `--cpu-only`, `--extra X` (repeatable, e.g. `--extra whisper`), `--no-ffmpeg`, `--no-frontend-check` (PowerShell: `-CpuOnly`, `-Extra X`, `-NoFfmpeg`, `-NoFrontendCheck`). The accelerator extras are mutually exclusive; see [docs/dependencies.md](docs/dependencies.md).

## Run

```bash
scripts/run.sh                 # videoflow serve (not implemented yet)
scripts/run.sh --help          # any other arguments go to the videoflow CLI
```
(`scripts\run.ps1` on Windows.)

## Develop

```bash
just test | smoke | lint | serve        # or: scripts/dev.sh test | smoke | lint | serve  (scripts\dev.ps1)
```

`test` runs the unit tier (CPU, synthetic media, no network; tests that need the `ml` extra are skipped without it); `smoke` runs the tests marked `smoke` (small CPU models, downloads them; needs an inference extra such as `cpu`/`smoke`, and `whisper` for the faster-whisper test). Synthetic samples are generated with FFmpeg (needs the `flite` filter) and cached under `VIDEOFLOW_SAMPLES_CACHE`.

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

- [Specification](docs/spec/README.md); the plan and decisions that override it are in [docs/spec/08-review-and-plan.md](docs/spec/08-review-and-plan.md)
- [Dependencies and accelerator matrix](docs/dependencies.md)
