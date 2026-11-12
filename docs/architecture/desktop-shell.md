# Desktop shell

Video-Flow runs as a desktop application. A PySide6 / Qt WebEngine window hosts the built React interface. The same process runs FastAPI on loopback, which serves that interface, the editor API and project media. Media work and inference run in child processes. The [architecture overview](overview.md) places the shell in the wider system. [Desktop runtime](../reference/desktop-runtime.md) covers setup, platform qualification, packaging recipes and licence notices.

## Process and thread model

| Component | Where it runs | Code |
|-----------|---------------|------|
| Qt application, `EditorWindow`, `QWebEngineView`, native dialogs and drops | Main thread | `desktop/host.py` |
| FastAPI app under uvicorn, with its own asyncio loop | Daemon thread `video-flow-backend` | `desktop/host.py` (`Backend`), `api/app.py` |
| Native selection requests to the backend | Short-lived daemon threads `native-media-selection` | `desktop/host.py` (`NativeBridge.select`) |
| FFmpeg and ffprobe (probe, preview media, renders) | Subprocesses | `media/`, `render/` |
| Speech, summary and keyword models | Worker processes in a `WorkerPool` | `jobs/workers.py`, `editor/imports.py` |

One process serves one open project at a time. The home screen closes it first (`close` action: imports, worker processes and renders are shut down and recreated idle), then opens or creates another in place (`switch_project`); none of this is allowed while an import or render is active. Renaming the open project releases it, renames its folder and opens it again. The window title follows the page title, which names the open project.

## Startup

1. `videoflow` with no subcommand runs `videoflow desktop`, and so do `scripts/run.sh` and `scripts/run.ps1` without arguments. The run scripts prepend `tools/ffmpeg/` to `PATH` when it exists. They use the existing `backend/.venv` CLI so missing inference dependencies appear in component setup; if it is absent they bootstrap with `uv run --inexact --extra desktop`. In a packaged build, `desktop_entry.py` calls `multiprocessing.freeze_support()` and then the same CLI. If the windowed executable has no console streams, its output goes to `Video-Flow/logs/desktop.log` under `%LOCALAPPDATA%`, or under `~/.local/share` on Linux.
2. `videoflow desktop [--project PATH]` opens the given bundle, or creates it if `project.json` is missing. Without `--project`, it reopens the most recent project of `recent-projects.json` (projects of the earlier per-user library are added to it once); with none, it starts on the home page with an internal placeholder bundle (`placeholder.video-flow` in the per-user data folder, `%LOCALAPPDATA%\Video-Flow` or `~/.local/share/video-flow`) that the user never sees. If PySide6 is missing, the command says to install the `desktop` extra.
3. `run_desktop` binds port 0 on `127.0.0.1` to pick a free port. It then creates a random launch token and a separate random desktop secret, and starts the backend thread, which imports and builds the API itself (`videoflow.api.app` is not imported before). Without waiting, it creates the Qt application and the window, which shows a native loading screen (“Opening Video-Flow…”) while the backend starts and Qt WebEngine initialises.
4. A 10 ms timer watches the backend. When uvicorn serves, the window (1440×980, minimum 850×720) loads `http://127.0.0.1:PORT/?token=TOKEN`; the web view replaces the loading screen once the page has loaded, so no blank page shows. If the backend fails, or does not serve within 30 seconds, the loading screen shows the error (also logged). The backend checks the token and answers with a 303 redirect to `/`. The redirect sets an `HttpOnly`, `SameSite=Strict` `videoflow` cookie, so the token does not stay in the URL. Later requests authenticate with the cookie.
5. At document creation, an injected script loads `qwebchannel.js` from Qt resources and connects to the host object. It sets `window.__videoflowDesktop = true` and exposes `window.videoFlowDesktop`. When the channel is ready, it dispatches `videoflow-ready`. The script runs in the main frame only.
6. Once the editor has loaded the project, it calls `ready()` on the bridge. The host then writes the startup timeline to the log, once: `Video-Flow startup (seconds since the process started): python …, qt …, window …, backend code …, backend …, page …, editor …` (`desktop/startup.py`). `python` is the time before Video-Flow's code ran (bootloader, interpreter), `qt` the Qt and host imports, `window` the window shown, `backend code` the API imported and built, `backend` the server serving, `page` the page loaded, `editor` the project shown. The packaged app writes it to `logs/desktop.log`; a run from a terminal prints it.

Only the app's own context menus open (the Project media menu, for example). The view has no context menu policy, and the page cancels every `contextmenu` event, so the browser menu (reload, back, copy address, inspect) never shows, in the desktop window or in a browser.

Built frontend assets come from `frontend/dist` in development. In a packaged build they come from the PyInstaller resource folder (`sys._MEIPASS`). If they are missing, the server answers 503 with build instructions. End users do not need Node, Vite or uv.

## Component readiness

After the interface loads, authenticated `/api/components` checks the selected inference runtimes and optional CUDA provider. The initial component popup opens for missing runtimes regardless of model weight presence. `/api/components/{component}/install` accepts only fixed component identifiers, requires native desktop mode, and runs a fixed uv command targeting the current non-frozen Python environment. It accepts no package names, paths or shell text from the renderer. Installs are refused while import/render jobs are active, are single-flight and cancellable, and are stopped during app shutdown. Restart is required after installation. Frozen applications direct the user to reinstall a complete release.

## Icons

All icon files live in `assets/icons/`: `video-flow.ico` (16 to 256 px) and `video-flow.png` (256 px). They are drawn by `scripts/make_icons.py` from the header mark (the tilted green square with the Film glyph); run it again after changing the mark. The packaged executable embeds the `.ico`. At startup the host sets the application and window icon from both files, so the window and its taskbar button show the mark. On Windows it also sets an explicit AppUserModelID (`VideoFlow.Desktop`), so a run from source gets its own taskbar entry instead of grouping under `python.exe`.

## Shutdown

Closing the window stops the view, deregisters the bridge object and calls `Backend.close()`. `QApplication.aboutToQuit` calls the same method, and `run_desktop` calls it again in `finally`. Repeated calls are harmless.

`Backend.close()` asks uvicorn to exit (graceful timeout 3 s, keep-alive 1 s) and waits up to 10 s. If the thread is still running, it forces the exit, cancels the remaining loop tasks and waits another 5 s. If the thread still has not stopped, it logs an error. The FastAPI lifespan closes the import service, which cancels jobs and shuts down the inference worker pool. It also closes the render jobs and the model downloads, which stops FFmpeg and worker children. The backend thread is a daemon thread, so it cannot keep the process alive.

## Security model

The renderer runs trusted first-party code, but the design still limits what it can reach.

- **Loopback only.** uvicorn binds `127.0.0.1` on a per-launch port.
- **Host and Origin.** Every request must carry exactly `Host: 127.0.0.1:PORT`, so other names such as `localhost` are rejected. Any `Origin` header must name the same host and port.
- **Authentication.** Every route, including static assets, needs the launch-token cookie. Responses carry `Referrer-Policy: no-referrer` and `X-Content-Type-Options: nosniff`.
- **Desktop secret.** Only the Python host knows the secret. It sends the secret in the `X-VideoFlow-Desktop` header on `/api/desktop/selection` and `/api/desktop/render-save`. The renderer never receives it, so it cannot call these endpoints. In `serve` mode there is no secret, and both endpoints answer 403.
- **Navigation.** `LocalPage` accepts only URLs with the trusted scheme, host and port and no user info. A link click in the main frame to an external `http(s)` URL opens in the system browser. Every other navigation is blocked.
- **Requests.** A profile-wide `QWebEngineUrlRequestInterceptor` blocks requests to any origin other than the trusted one. `data:`, `blob:` and `qrc:` URLs are allowed.
- **Page settings.** Local content cannot read `file://` URLs or remote URLs, and JavaScript cannot open windows. Autoplay does not require a user gesture.
- **Bridge.** Every slot does nothing unless the view's current URL is trusted. The bridge has no general filesystem, shell or network capability.

### Native selections are the only way to name new source paths

A source path enters the project only through a native dialog or a drop.

1. The host sends the chosen paths to `/api/desktop/selection` with the desktop secret.
2. `SelectionGrants` resolves each path to its canonical form. It requires an existing file with a media extension from `MEDIA_EXTENSIONS`. Each file gets a random handle that is valid for one hour, and the renderer receives `{handle, name}`.
3. The renderer redeems a handle once, with `/api/native-import` or `/api/native-relink`. A relink handle is bound to the asset ID it was issued for, and an import handle cannot be used to relink. Grants are reset when the project switches.

`PATCH /api/project` also guards edits that the renderer submits:

- It accepts only `SetEditor`, `SetSettings`, `RenameProject`, `RemoveAsset` and `Batch`.
- `AddAsset` must reproduce an asset that the backend already knows exactly.
- `RelinkAsset` may only use a path that the backend has already recorded for that asset. This lets undo and redo of imports and relinks replay without letting the renderer invent paths.

Native selections work outside any configured root. Grants cover only the selected files, never their folders.

## Bridge surface

The host object is registered on the `QWebChannel` as `desktop`. The injected script wraps it as `window.videoFlowDesktop`. `frontend/src/desktop.ts` declares the same surface for the frontend.

| JS call / event | Host side | Effect |
|-----------------|-----------|--------|
| `pickFiles()` | `QFileDialog.getOpenFileNames`, filtered to media extensions | Issues grants, then `videoflow-selection` with `{selections, assetId: null}` |
| `pickFolder(purpose)` | `QFileDialog.getExistingDirectory` | Issues a folder handle (`workdir` for a new project, `project` for a `.video-flow` folder) through `/api/desktop/folder`, then `videoflow-folder` with `{handle, name, path, purpose}` |
| `relink(assetId)` | `QFileDialog.getOpenFileName` | Issues one grant bound to `assetId`, then `videoflow-selection` |
| `saveRenderedVideo(id)` | `QFileDialog.getSaveFileName` for `*.mp4` | Calls `/api/desktop/render-save` |
| `setZoom(factor)` | `QWebEngineView.setZoomFactor`, clamped to 0.5–2.0 | Page zoom |
| `ready()` | Marks the end of startup | Writes the startup timeline to the log, once |
| `videoflow-error` event | `failed` signal | Shows the message in the editor |

## Native file workflows

- **Import.** The Import button calls `pickFiles()`. The resulting handles feed the import dialog, which submits them one at a time to `/api/native-import`, with or without analysis. Sequential processing, progress and cancellation follow [importing media](../features/import-analysis/importing.md). Originals are referenced in place. Preview media, thumbnails and waveforms go in the application cache.
- **Drop.** An event filter on the web view and on every widget Qt WebEngine adds inside it (drops land on its render widget) handles drag-enter, drag-move and drop events. It is not installed on the whole application: an application-wide Python event filter crashes Qt WebEngine on Linux. It accepts a drop only if every URL is a local file. It keeps files with media extensions and silently ignores the rest. The paths then follow the same grant flow as the picker. The web page never sees the file contents or the paths.
- **Relink.** Assets whose source file is missing are listed as offline by `GET /api/project`. In the desktop app they show a Relink action. `/api/native-relink` requires the selected file's content hash to match the asset's fingerprint. It then commits `RelinkAsset`, adding a relative path when the file is under the bundle's parent folder. The result is one undo step, and trims and links are kept.
- **Save as MP4.** After a render finishes, the host asks for a destination. `/api/desktop/render-save` accepts only a completed render inside the bundle's `renders/` folder and a `.mp4` destination that is not one of the project's original files. It copies the render to a temporary file and moves it into place with `os.replace`. The MP4 export itself is described in [render and export](../features/output/render-and-export.md).
- **Open cache folder.** Settings calls `POST /api/cache/open`. The backend creates the application cache folder if needed and opens it with `runtime.open_folder`: `os.startfile` on Windows, `xdg-open` on Linux. This does not go through the bridge. See [workspace zones](../features/editing/workspace-zones.md).
- **Interface zoom.** The status-bar controls and Ctrl+wheel set a zoom factor from 50% to 200%. The desktop app sends it to `setZoom` and applies it again on `videoflow-ready`.

## Media playback

Qt WebEngine (PySide6 wheels) has no H.264 or AAC decoder, so the editor plays WebM (VP9 video, Opus sound), which browsers play too. `editor/previews.py` makes it in two stages ([preview media](../features/import-analysis/importing.md#preview-media)):

1. **Quick pass**, run by the import (phase "Preparing preview"): one FFmpeg run decodes keyframes only (`-skip_frame nokey`) and writes one 360p JPEG per second (`fps=1:start_time=0`, so still *n* is the last keyframe at or before second *n*) and the sound as `audio.webm` (Opus 96 kb/s). Files go to `cache/<project>/previews/<key>/`, written in a temporary folder then moved into place. About 0.6 s per minute of 1080p footage, against 8 s or more for a full transcode.
2. **Background video**: a single asyncio worker takes one source at a time from a queue and encodes the original directly to `cache/<project>/proxies/<key>.webm`: 540p (`media/proxy.py` size, rotation, HDR tone mapping and CFR filters), libvpx-vp9 realtime (`-cpu-used 8`, row-mt, CRF 35), a keyframe every second, tagged 8-bit BT.709, Opus, half the processors, low process priority (`BELOW_NORMAL_PRIORITY_CLASS` on Windows, nice 10 on Linux). When it is done the quick-pass folder is deleted. Failures are kept per source and reported; editing goes on with the stills.

The key is the content hash plus the preview version; WebM files of earlier versions (key `:webm-v1`) are still used. Sources missing a video are queued when a project opens; a still or media request moves a source to the front of the queue. Still images and WAV, MP3, FLAC, OGG and Opus audio need no preview (`plays_as_is`).

Endpoints (only assets of the open project, HTTP byte ranges through Starlette's `FileResponse`):

- `GET /api/media/{assetId}`: the image PNG, the original for playable audio, else the preview video, else the quick-pass sound; 409 while nothing exists yet.
- `GET /api/previews`: state of each source (`ready`, `stills`, `pending`, `failed`), still count, progress and error; the frontend (`frontend/src/previews.ts`) polls it every 1.5 s while one is not ready.
- `GET /api/previews/{assetId}/still/{second}`: the still of that second (clamped to the last one), cacheable for 10 minutes.
- `GET /api/previews/{assetId}/audio`: the quick-pass sound.

The preview shows the still of the current second in an `<img>` until the video exists, then switches to the `<video>`; audio clips play the quick-pass sound meanwhile. All playback files are generated caches and never copies of the originals.

While a dialog is open (Settings, import, help, save, project home dialogs), the editor workspace is hidden with `visibility: hidden` and only the dialog stays visible. Video layers repainting under a dialog corrupted compositing tiles in Qt WebEngine on Windows; taking them out of compositing avoids it.

## Browser diagnostic mode

`videoflow serve [--project PATH] [--port 8765] [--media-root DIR ...] [--no-open-browser]` runs the same API and interface in a normal browser. It prints the launch URL with its token and, unless disabled, opens it after 1.5 seconds. The default project is `edit.video-flow` in the current folder. It differs from the desktop app in these ways:

- There is no bridge and no desktop secret. Native selection, relink and render-save endpoints answer 403. `GET /api/project` reports `desktop: false`.
- Import uses typed paths through `/api/import-path`. A path is accepted only if it is under a `--media-root`, which defaults to the bundle's parent folder, and has a media extension. File drops show a message instead of importing.
- MP4 results download from `/api/renders/{id}/file` instead of a save dialog. Interface zoom uses CSS `zoom` instead of page zoom.
- The byte-upload route `/api/uploads/...` exists but is off. It needs `allow_uploads=True` in `create_app`, which no command sets, and it is always refused when a desktop secret is present.

The hidden `videoflow desktop-check MEDIA OUTPUT [--features]` command, also run by `scripts/desktop_smoke.py`, drives the real `EditorWindow` against a new disposable project. It writes a report and a screenshot. [Desktop runtime](../reference/desktop-runtime.md) describes what it covers.

## Packaging

`scripts/desktop.spec` builds a PyInstaller one-folder release named `Video-Flow`, without a console window. The entry point is `desktop_entry.py`.

- **Bundled data:** `frontend/dist`, `engines/manifest.toml`, the Inter fonts, the app icons, OpenTimelineIO adapter data and metadata, and a notices file.
- **Icon:** the executable embeds `assets/icons/video-flow.ico` (Windows only; PyInstaller ignores it on Linux).
- **Hidden imports:** the analysis engines and the OTIO adapters, which PyInstaller does not detect.
- **Windows runtime:** the MSVC runtime DLLs are pinned to the ones shipped with PySide6, and unsuffixed ICU DLLs are excluded so that Qt uses the Windows system ICU.

Some files are not in the bundle and live beside the executable. `runtime.application_dir()` returns the folder of the executable when frozen, or the repository root in development.

- FFmpeg goes in `tools/ffmpeg/` or on `PATH`.
- Model weights go in `models/`. `runtime.model_directory()` also points the Hugging Face caches there.
- Preferences are stored in `settings.json`.

## Platform status

The shell code is the same on Windows and Linux. Path handling uses pathlib, and `open_folder` picks the platform opener. Windows 11 x64 is qualified with the native check and a packaged build. Linux x86_64 and Windows ARM64 are not yet qualified. [Desktop runtime](../reference/desktop-runtime.md) holds the qualification records, the known codec limits of the tested Qt wheel and the remaining gates.
