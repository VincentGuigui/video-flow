#!/usr/bin/env bash
# Start the app (`videoflow serve`) or pass any other CLI arguments through.
#   scripts/run.sh                 -> videoflow serve
#   scripts/run.sh --help          -> videoflow --help
#   scripts/run.sh analyse DIR     -> videoflow analyse DIR
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [ -d "$ROOT/tools/ffmpeg" ]; then
  export PATH="$ROOT/tools/ffmpeg:$PATH"
fi
cd "$ROOT/backend"
if [ $# -eq 0 ]; then
  set -- serve
fi
exec uv run videoflow "$@"
