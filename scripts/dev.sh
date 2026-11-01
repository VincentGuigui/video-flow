#!/usr/bin/env bash
# Plain equivalent of the justfile: scripts/dev.sh {test|smoke|lint|serve|build|package} [args...]
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cmd="${1:-}"
[ $# -gt 0 ] && shift

build_frontend() {
  cd "$ROOT/frontend"
  [ -d node_modules ] || npm ci
  npm run build
}

case "$cmd" in
  build) build_frontend; exit 0 ;;
  package)
    build_frontend
    cd "$ROOT"
    # --inexact keeps the installed inference extras; desktop and PyInstaller are added.
    # package_release.py keeps models/, tools/, settings.json... beside the executable.
    exec uv run --project backend --inexact --extra desktop --group packaging \
      python scripts/package_release.py "$@"
    ;;
esac
cd "$ROOT/backend"
case "$cmd" in
  test) exec uv run pytest "$@" ;;
  smoke) exec uv run pytest -m smoke "$@" ;;
  lint)
    uv run ruff check .
    uv run ruff format --check .
    exec uv run mypy
    ;;
  serve) exec uv run videoflow serve "$@" ;;
  *) echo "usage: scripts/dev.sh {test|smoke|lint|serve|build|package} [args...]" >&2; exit 2 ;;
esac
