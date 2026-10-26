# Workspace layout

`backend/`, `frontend/`, `scripts/` and `docs/` contain maintained source.
`tools/` contains installed runtimes, FFmpeg and packaged builds; keep it out of Git.
`.cache/` contains generated smoke fixtures, reports and build intermediates.
Project bundles and original media are user data and are never cleanup targets.
The abandoned empty `.tools/` bootstrap directory has been removed; installers use `tools/`.
