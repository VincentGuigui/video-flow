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
