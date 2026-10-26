# AGENTS.md

Guidance for coding agents working on Video-Flow: a local-first desktop video assembly tool for rushes and retakes. It targets Windows and Linux. AI work runs on the NPU, then the GPU, then the CPU.

## Layout

| Path | Content |
|------|---------|
| `backend/` | Python 3.13 package `videoflow` (uv): FastAPI API, editor model, media, analysis, render, exporters, PySide6 desktop shell |
| `frontend/` | React + Vite editor UI (npm). `src/model.ts` holds the interactive edit model |
| `scripts/` | Install, run and dev scripts (`*.sh` Linux, `*.ps1` Windows), sample generator, desktop smoke test |
| `docs/` | All documentation (see below) |

## Documentation

- `README.md`: essentials, install, run, usage.
- `docs/spec/`: the specification, numbered files indexed in `docs/spec/README.md`. 01–07 are the original spec. 08 onwards are dated revisions, and later revisions supersede earlier ones where they conflict.
- `docs/dependencies.md`: every runtime and dev dependency with version, licence and accelerator matrix. Update it whenever a dependency changes.
- `docs/desktop-runtime.md`, `docs/workspace-layout.md`, `docs/validation-*.md`: runtime notes and validation records.

## Rules

- **Commits:** atomic, one functional change per commit, concise functional message. No `Co-Authored-By` or other AI co-author trailer.
- **Specs:** document every feature in the spec. Either update the relevant `docs/spec` file or add a new numbered revision and list it in `docs/spec/README.md`. When a feature is removed or replaced, delete or amend its description everywhere in `docs/` so no spec describes behaviour that no longer exists.
- No refactoring, rollback, framework or major-version change without asking first.
- Keep `README.md` current with the essentials.
- Code must work on Windows and Linux: pathlib, no `shell=True`, and provide both `.sh` and `.ps1` scripts.
- English everywhere (code, comments, docs, commit messages).

## Checks

```bash
cd backend && uv run pytest && uv run ruff check . && uv run ruff format --check . && uv run mypy
cd frontend && npm test && npm run typecheck && npx prettier --check src
```

`uv run pytest -m smoke` runs the model-downloading tier. Tests use synthetic media and must not need network in the unit tier.
