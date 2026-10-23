#!/usr/bin/env bash
# Plain equivalent of the justfile: scripts/dev.sh {test|smoke|lint|serve} [args...]
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT/backend"
cmd="${1:-}"
[ $# -gt 0 ] && shift
case "$cmd" in
  test) exec uv run pytest "$@" ;;
  smoke) exec uv run pytest -m smoke "$@" ;;
  lint)
    uv run ruff check .
    uv run ruff format --check .
    exec uv run mypy
    ;;
  serve) exec uv run videoflow serve "$@" ;;
  *) echo "usage: scripts/dev.sh {test|smoke|lint|serve} [args...]" >&2; exit 2 ;;
esac
