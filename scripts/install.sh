#!/usr/bin/env bash
# Video-Flow installer for Linux.
#   scripts/install.sh [--cpu-only] [--extra X]... [--no-ffmpeg] [--no-frontend-check] [--help]
# Installs uv (if missing), Python 3.13, the backend with the accelerator extra matching the
# detected hardware, FFmpeg >= 6.1 (system one if recent enough, else a static build in
# tools/ffmpeg/) and checks Node 22 + pnpm (only needed to build the frontend).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FFMPEG_MIN="6.1"
FFMPEG_STATIC_URL="${VIDEOFLOW_FFMPEG_URL:-https://johnvansickle.com/ffmpeg/old-releases/ffmpeg-7.0.2-amd64-static.tar.xz}"
FFMPEG_STATIC_SHA256="${VIDEOFLOW_FFMPEG_SHA256:-}"

CPU_ONLY=0
NO_FFMPEG=0
NO_FRONTEND=0
EXTRAS=()

log() { printf '[install] %s\n' "$*"; }
warn() { printf '[install] WARNING: %s\n' "$*" >&2; }
die() { printf '[install] ERROR: %s\n' "$*" >&2; exit 1; }

usage() {
  sed -n '2,6p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
  cat <<'USAGE'

Flags:
  --cpu-only           skip hardware detection, install the CPU extra
  --extra X            add extra X (repeatable). Accelerator extras are mutually exclusive:
                       cpu | openvino | cuda | directml | qnn. Others: whisper
  --no-ffmpeg          do not check or install FFmpeg
  --no-frontend-check  do not check Node / pnpm
USAGE
}

while [ $# -gt 0 ]; do
  case "$1" in
    --cpu-only) CPU_ONLY=1 ;;
    --extra) shift; [ $# -gt 0 ] || die "--extra needs a value"; EXTRAS+=("$1") ;;
    --no-ffmpeg) NO_FFMPEG=1 ;;
    --no-frontend-check) NO_FRONTEND=1 ;;
    -h|--help) usage; exit 0 ;;
    *) usage >&2; die "unknown argument: $1" ;;
  esac
  shift
done

version_ge() { [ "$(printf '%s\n%s\n' "$2" "$1" | sort -V | head -n1)" = "$2" ]; }

have() { command -v "$1" >/dev/null 2>&1; }

fetch() { # url dest
  if have curl; then curl -fsSL --retry 3 -o "$2" "$1"
  elif have wget; then wget -q -O "$2" "$1"
  else die "curl or wget is required"; fi
}

install_uv() {
  if have uv; then log "uv found: $(uv --version)"; return; fi
  log "installing uv"
  local tmp; tmp="$(mktemp)"
  fetch "https://astral.sh/uv/install.sh" "$tmp"
  sh "$tmp"
  rm -f "$tmp"
  export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
  have uv || die "uv installed but not on PATH; add ~/.local/bin to PATH and rerun"
}

detect_extra() {
  local arch; arch="$(uname -m)"
  local pci=""
  if have lspci; then pci="$(lspci 2>/dev/null || true)"; fi
  if [ -e /dev/accel/accel0 ] || { have lsmod && lsmod 2>/dev/null | grep -q '^intel_vpu'; } \
     || printf '%s' "$pci" | grep -qi 'Neural Processing Unit\|Intel.*NPU'; then
    log "detected Intel NPU"; echo openvino; return
  fi
  if printf '%s' "$pci" | grep -qi 'amdxdna\|Ryzen AI\|IPU' || [ -e /dev/accel/accel1 ]; then
    warn "AMD Ryzen AI NPU detected: the VitisAI EP needs the Ryzen AI SDK (Windows only); see docs/dependencies.md. Using the CPU extra."
  fi
  if have nvidia-smi && nvidia-smi -L >/dev/null 2>&1 && [ "$arch" = "x86_64" ]; then
    log "detected NVIDIA GPU"; echo cuda; return
  fi
  if printf '%s' "$pci" | grep -qi 'nvidia' && [ "$arch" = "x86_64" ]; then
    warn "NVIDIA GPU found but the driver (nvidia-smi) is not working; using the CPU extra."
  fi
  echo cpu
}

ffmpeg_version() { # prints "X.Y" or nothing
  "$1" -version 2>/dev/null | sed -n '1s/^ffmpeg version [nN]\{0,1\}\([0-9]\{1,\}\.[0-9]\{1,\}\).*/\1/p'
}

install_ffmpeg() {
  local dir="$ROOT/tools/ffmpeg"
  if [ -x "$dir/ffmpeg" ] && [ -x "$dir/ffprobe" ]; then
    local v; v="$(ffmpeg_version "$dir/ffmpeg")"
    if [ -n "$v" ] && version_ge "$v" "$FFMPEG_MIN"; then log "local FFmpeg $v in tools/ffmpeg"; return; fi
  fi
  if have ffmpeg && have ffprobe; then
    local v; v="$(ffmpeg_version "$(command -v ffmpeg)")"
    if [ -n "$v" ] && version_ge "$v" "$FFMPEG_MIN"; then log "system FFmpeg $v is recent enough"; return; fi
    warn "system FFmpeg '${v:-unknown}' is older than $FFMPEG_MIN"
  fi
  if [ "$(uname -m)" != "x86_64" ]; then
    die "no static FFmpeg build is pinned for $(uname -m); install FFmpeg >= $FFMPEG_MIN with your package manager"
  fi
  log "downloading static FFmpeg into tools/ffmpeg"
  local tmp; tmp="$(mktemp -d)"
  fetch "$FFMPEG_STATIC_URL" "$tmp/ffmpeg.tar.xz"
  if [ -n "$FFMPEG_STATIC_SHA256" ]; then
    echo "$FFMPEG_STATIC_SHA256  $tmp/ffmpeg.tar.xz" | sha256sum -c - || die "FFmpeg checksum mismatch"
  else
    warn "VIDEOFLOW_FFMPEG_SHA256 not set: archive integrity not verified"
  fi
  tar -xf "$tmp/ffmpeg.tar.xz" -C "$tmp"
  mkdir -p "$dir"
  local src; src="$(find "$tmp" -maxdepth 2 -name ffmpeg -type f | head -n1)"
  [ -n "$src" ] || die "ffmpeg binary not found in archive"
  cp "$(dirname "$src")/ffmpeg" "$(dirname "$src")/ffprobe" "$dir/"
  chmod +x "$dir/ffmpeg" "$dir/ffprobe"
  rm -rf "$tmp"
  log "installed FFmpeg $(ffmpeg_version "$dir/ffmpeg") in tools/ffmpeg"
}

check_frontend_tools() {
  if have node && [ "$(node -p 'process.versions.node.split(".")[0]')" -ge 22 ]; then
    log "node $(node --version)"
  else
    warn "Node 22+ not found (only needed to build the frontend). Install it from https://nodejs.org or with fnm/nvm."
  fi
  if have pnpm; then log "pnpm $(pnpm --version)"
  elif have corepack; then log "pnpm missing: enable with 'corepack enable pnpm'"
  else warn "pnpm not found (only needed to build the frontend): npm i -g pnpm"; fi
}

install_uv
log "ensuring Python 3.13"
uv python install 3.13

if [ "$NO_FFMPEG" -eq 0 ]; then install_ffmpeg; fi
if [ "$NO_FRONTEND" -eq 0 ]; then check_frontend_tools; fi

ACCEL=""
for e in "${EXTRAS[@]+"${EXTRAS[@]}"}"; do
  case "$e" in cpu|smoke|openvino|cuda|directml|qnn) ACCEL="$e" ;; esac
done
if [ -z "$ACCEL" ]; then
  if [ "$CPU_ONLY" -eq 1 ]; then ACCEL=cpu; else ACCEL="$(detect_extra)"; fi
  EXTRAS+=("$ACCEL")
fi
log "accelerator extra: $ACCEL"

args=()
for e in "${EXTRAS[@]}"; do args+=(--extra "$e"); done
(cd "$ROOT/backend" && uv sync "${args[@]}")

log "done. Run: scripts/run.sh   (tests: scripts/dev.sh test)"
