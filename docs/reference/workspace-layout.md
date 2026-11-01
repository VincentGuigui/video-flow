# Workspace layout

`backend/`, `frontend/`, `scripts/` and `docs/` contain maintained source.
`tools/` contains installed development runtimes and FFmpeg; keep it out of Git.
`releases/Video-Flow/` contains the runnable desktop distribution, including its `_internal/`, `models/` and `tools/` runtime subdirectories. Keep generated releases out of Git.
The `tools/` subdirectory inside a release contains that application’s FFmpeg binaries; it is separate from the repository’s development `tools/` directory.
`.cache/` contains generated smoke fixtures, reports and build intermediates.
Project bundles and original media are user data and are never cleanup targets.
The abandoned empty `.tools/` bootstrap directory has been removed; installers use `tools/`.
