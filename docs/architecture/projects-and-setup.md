# Projects, cache, FFmpeg and updates: how they work

Technical details behind [projects](../features/getting-started/projects.md) and [FFmpeg setup](../features/getting-started/ffmpeg-setup.md); the bundle format is in [data model](data-model.md).

## Project folder and working folder

- A project is a `<name>.video-flow` folder inside the user's working folder, the folder that holds the original media. It contains `project.json` (the edit), `history.jsonl`, `analysis/`, `features/`, `exports/` and `renders/`.
- Media are referenced relative to the working folder (`relPath`, with the absolute path kept as a fallback). Media outside the working folder are referenced with `../` paths, or only absolutely when they are on another Windows drive.
- Rebuildable caches (proxies, thumbnails, waveforms, title pictures, render work files) are not in the project: they live in the application cache (`cache/<project id>/` beside the executable; `VIDEOFLOW_CACHE_DIR` overrides). A project from an earlier version still holding a `cache/` folder has it deleted when it opens.
- The recent list is `recent-projects.json` in `%LOCALAPPDATA%\Video-Flow` on Windows, `~/.local/share/video-flow` on Linux (at most 20, most recent first). Projects created by earlier versions in the per-user `Video-Flow` library (`*.videoflow`) are added to it the first time, and open as before.

## Home page rules

- Closing the open project releases its workers, renders and media and clears the editor.
- **New project** creates `<working folder>/<name>.video-flow`. Names are kept file-system safe (`< > : " / \ | ? *` removed); an existing folder of that name is refused.
- **Open project…** accepts only valid project folders: named `*.video-flow` (or `*.videoflow` from earlier versions) and containing `project.json`.
- **Rename** renames the project and its folder in the same working folder. **Remove from list** only forgets the project. **Delete** moves the `<name>.video-flow` folder to the system trash after a confirmation; the media are never touched.
- **Save as** copies the project into the same working folder as `<new name>.video-flow` (decisions, analysis and features; media references stay relative) and opens the copy. Save names an untitled project by renaming its folder.
- The desktop app reopens the most recent project of the list. `videoflow desktop --project PATH` opens or creates a given folder.

## Security

The interface never names folders itself in the desktop app: the native folder dialog issues a single-use handle (`POST /api/desktop/folder`, desktop secret only) for a working folder or a project folder (one that holds `project.json`), which the project action redeems. In a browser, typed folders must be under a `--media-root`.

## Cache folder

Settings → **Cache** lists the cache per project (proxies, thumbnails, waveforms, title pictures and render work files). **Open cache folder** opens it in the system file manager (Explorer on Windows, `xdg-open` on Linux); **Clear cache** deletes it, refused while an import or render runs; files still in use are kept and reported. Everything is rebuilt on demand.

## FFmpeg

### Where FFmpeg is found

`media/caps.py` looks, in order, at the paths set in settings, at `tools/ffmpeg/` beside the application (the repository root in development), then at `PATH`. A build older than 6.1 counts as missing.

### Capability probe

What a build can do (version, filters, encoders, hardware decoders, xfade transitions, graph-file flag) comes from six short FFmpeg runs, made side by side (`media/caps.py`, `probe_caps`). The result is kept per user in `ffmpeg-caps.json` (in `%LOCALAPPDATA%\Video-Flow`, or `~/.local/share/video-flow`), keyed by the paths, sizes and modification times of `ffmpeg` and `ffprobe`: a launch with the same build runs no FFmpeg at all, and a new or replaced build (an install, another PATH) is probed once. A damaged or unwritable file only costs a probe. `GET /api/ffmpeg` looks for the binaries again each time and probes only when they changed (about 3 ms instead of 300 ms here).

### Pinned builds

`backend/videoflow/media/ffmpeg_install.py` pins one static build per platform, by URL and SHA-256:

| Platform | Build | Distributor | Licence |
|----------|-------|-------------|---------|
| Windows x64 | 7.1.1 full build (includes `flite` for the sample generator) | [gyan.dev](https://www.gyan.dev/ffmpeg/builds/) | GPL-3.0 |
| Linux x64 | 7.0.2 static | [John Van Sickle](https://johnvansickle.com/ffmpeg/) | GPL-3.0 |

No build is pinned for other systems (Windows ARM64, Linux ARM64): FFmpeg is installed manually there. The distributor builds the archive and provides its source code; Video-Flow installs it unchanged. Only `ffmpeg`, `ffprobe` and the archive's licence and readme files (`LICENSE` and `README.txt`, or `GPLv3.txt` and `readme.txt`) are copied into `tools/ffmpeg/`. If the downloaded archive does not match its checksum (for example because the distributor replaced it), nothing is installed. `scripts/install.sh` and `scripts/install.ps1` pin the same builds; a test checks that they agree.

### Install window and API

The FFmpeg window shows the pinned build (version, distributor, licence, download size, source URL, target folder), and downloads nothing until **Download and install** is clicked. API: `GET /api/ffmpeg` (status, pinned build, download job), `POST /api/ffmpeg/install`, `POST /api/ffmpeg/cancel`. Once installed, the app uses the build at once (no restart).

### Install scripts

`scripts/install.sh` and `scripts/install.ps1` keep a local `tools/ffmpeg/` or a system FFmpeg when it is 6.1 or newer. Otherwise they print the source, distributor and licence and ask before downloading. `--yes` (`-Yes` in PowerShell) accepts without asking; without a terminal and without `--yes`, the download is skipped with instructions. `--no-ffmpeg` (`-NoFfmpeg`) skips the check. `VIDEOFLOW_FFMPEG_URL` and `VIDEOFLOW_FFMPEG_SHA256` select another archive; the checksum is always verified.

## Updates

Code: `backend/videoflow/updates.py` (check, download, apply, cleanup), the `/api/update` endpoints in `api/app.py`, the hidden `apply-update` command in `cli.py`, the `quit` slot of the desktop bridge (`desktop/host.py`), `frontend/src/updates.ts` and `frontend/src/ui/UpdateDialog.tsx`. User page: [updates](../features/getting-started/updates.md).

- **Check.** `GET /api/update?start=true` reads `https://api.github.com/repos/VincentGuigui/video-flow/releases/latest` once per run (6 s timeout, user agent `Video-Flow/<version>`; `VIDEOFLOW_UPDATE_URL` replaces the URL for tests); `refresh=true` asks again (Settings). The latest endpoint never returns drafts or pre-releases. The tag `v<major>.<minor>.<patch>` is compared numerically with `videoflow.__version__`. The notes are the `* ` lines after the "What's new" heading of the release text ([automated releases](../reference/github-releases.md)). Errors (offline, rate limit of 60 requests per hour) are silent at start and a 502 from Settings. Preferences: `checkUpdates` (default on), `skippedUpdate` (the version skipped).
- **Installable** when the app runs frozen (PyInstaller), on windows-x64 or linux-x64, the release has `Video-Flow-<version>-<platform>.zip` and its `.zip.sha256`, and `updates/` can be written beside the executable. Otherwise the window shows the reason and the release page.
- **Download** (`POST /api/update/install`, polled through `GET /api/update`, `POST /api/update/cancel`): the checksum file, then the ZIP into `updates/<version>/`, hashed while written; a mismatch stops before unpacking. Entries are unpacked with a path check (no entry outside the folder) and their Unix modes; the result must hold `Video-Flow/<executable>` and `Video-Flow/_internal/`.
- **Apply** (`POST /api/update/restart`, refused while imports or renders run): the running app starts `<new>/Video-Flow apply-update --target <application folder> --pid <its pid>` detached (Windows `DETACHED_PROCESS`, Linux new session), and the frontend calls the bridge's `quit`, which closes the window and the backend. The new process waits up to 120 s for that pid to end, moves every entry of the target that its own folder also has (executable, `_internal/`, shortcut script) into `updates/previous-<time>/`, copies its own entries in place, then starts the target executable. On any error the copied entries are removed and the moved ones restored, the previous executable is started and the error logged in `update.log`. `apply-update --target --pid` is a contract between versions: an installed version runs the command of the downloaded one.
- **Cleanup.** A frozen app deletes `updates/` at start in a background thread, unless it runs from inside it.

