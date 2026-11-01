# Plain-script equivalents live in scripts/dev.sh and scripts/dev.ps1.
set windows-shell := ["powershell.exe", "-NoLogo", "-Command"]

default:
    @just --list

# Unit tests (no network, no models)
test *args:
    cd backend && uv run pytest {{args}}

# Smoke tier: CPU models, may download
smoke *args:
    cd backend && uv run pytest -m smoke {{args}}

lint:
    cd backend && uv run ruff check . && uv run ruff format --check . && uv run mypy

serve *args:
    cd backend && uv run videoflow serve {{args}}

# Rebuild the editor interface (frontend/dist), used by the run scripts and the app
build:
    cd frontend && npm run build

# Frontend, then the one-folder desktop app in releases/Video-Flow
package: build
    uv run --project backend --inexact --extra desktop --group packaging pyinstaller --noconfirm --distpath releases --workpath .cache/pyinstaller scripts/desktop.spec
