# Updates

Video-Flow can update itself from its releases on GitHub. Your projects, AI models, FFmpeg, cache and settings are kept.

## At start

When Video-Flow starts, it asks GitHub for the latest release. If it is newer than yours, a window opens before any other (before the FFmpeg and AI models windows):

- **Video-Flow 0.37.0 is available**, the version you have, and what is new.
- **Update now**: downloads the version for your system (Windows or Linux) and checks it against its SHA-256. The progress is shown; **Cancel** stops it.
- **Restart and update**, once downloaded: Video-Flow closes, replaces its own files with the new version and opens again, on your last project. Finish or cancel imports and renders first.
- **Later**: closes the window; it opens again at the next start.
- **Skip this version**: not offered again at start; a newer version will be.

Without a network, or when GitHub does not answer within a few seconds, Video-Flow starts normally, with no message.

## From Settings

- **Check for a new version at start**: turn the check off or on (then **Save settings**).
- **Check for updates**: asks GitHub now, even for a skipped version, and opens the same window, or says that you have the latest version.

## Good to know

- Only the application files are replaced (the program and its `_internal` folder). Everything else beside it stays: `models/`, `tools/` (FFmpeg), `cache/`, `settings.json`, the logs and any file you put there. The previous version is kept in `updates/` until the next start, then deleted.
- If the update cannot be applied (a file locked, a full disk), the previous version is put back and opened again; the reason is in `update.log` in the logs folder (`%LOCALAPPDATA%\Video-Flow\logs` on Windows, `~/.local/share/video-flow/logs` on Linux).
- The application folder must be writable by you. If it is not (installed in a protected folder), or when you run Video-Flow from its source code, the window gives the address of the release to download it yourself.
- Pre-releases and drafts are never offered.

## Technical notes

Rules and code are in [projects, cache and FFmpeg](../../architecture/projects-and-setup.md#updates); tests in the [updates validation](../../validation/2026-11-12-updates.md).
