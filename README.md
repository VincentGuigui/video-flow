# Video-Flow

Local-first assembly tool for footage shot with many retakes: ingest rushes, transcribe and analyse them, group equivalent takes into beats, compare alternatives side by side, then render with FFmpeg or export to an editor (OpenTimelineIO, FCPXML, EDL, Camtasia).

Status: specification complete (see below), implementation in progress (backend scaffold).

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
scripts/run.sh                 # videoflow serve
scripts/run.sh --help          # any other arguments go to the videoflow CLI
```
(`scripts\run.ps1` on Windows.)

## Develop

```bash
just test | smoke | lint | serve        # or: scripts/dev.sh test | smoke | lint | serve  (scripts\dev.ps1)
```

`test` runs the unit tier (CPU, synthetic media, no network); `smoke` runs the tests marked `smoke` (small CPU models, may download).

## Documentation

- [Specification](docs/spec/README.md); the plan and decisions that override it are in [docs/spec/08-review-and-plan.md](docs/spec/08-review-and-plan.md)
- [Dependencies and accelerator matrix](docs/dependencies.md)
