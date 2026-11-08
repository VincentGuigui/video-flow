#!/usr/bin/env bash
# Start the native desktop app or pass any other CLI arguments through.
#   scripts/run.sh                 -> videoflow desktop
#   scripts/run.sh --help          -> videoflow --help
#   scripts/run.sh analyse DIR     -> videoflow analyse DIR
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [ -d "$ROOT/tools/ffmpeg" ]; then
  export PATH="$ROOT/tools/ffmpeg:$PATH"
fi
cd "$ROOT/backend"
if [ $# -eq 0 ]; then
  set -- desktop
fi
# Existing environments show missing inference dependencies in component setup.
if [ -x "$ROOT/backend/.venv/bin/videoflow" ]; then
  exec "$ROOT/backend/.venv/bin/videoflow" "$@"
fi
exec uv run --inexact --extra desktop videoflow "$@"
