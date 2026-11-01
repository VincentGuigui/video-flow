#!/usr/bin/env bash
# Adds Video-Flow (with its icon) to the application menu of the current user.
# Keep this file next to the Video-Flow executable; run it again after moving the folder.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP="$HERE/Video-Flow"
[ -x "$APP" ] || { echo "Video-Flow was not found next to this script." >&2; exit 1; }
MENU="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
mkdir -p "$MENU"
cat > "$MENU/video-flow.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=Video-Flow
Comment=Assemble footage shot with many retakes
Exec="$APP"
Path=$HERE
Icon=$HERE/_internal/assets/icons/video-flow.png
Terminal=false
Categories=AudioVideo;Video;AudioVideoEditing;
DESKTOP
command -v update-desktop-database >/dev/null && update-desktop-database "$MENU" || true
echo "Video-Flow was added to the application menu."
