# FFmpeg setup

Video-Flow needs FFmpeg 6.1 or newer (`ffmpeg` and `ffprobe`) to read media, make previews and thumbnails, and render. FFmpeg is a separate program: Video-Flow runs its executables and never links to it or modifies it, so Video-Flow's own licence is unaffected. FFmpeg is not bundled in the releases.

## Where FFmpeg is found

`media/caps.py` looks, in order, at the paths set in settings, at `tools/ffmpeg/` beside the application (the repository root in development), then at `PATH`. A build older than 6.1 counts as missing.

## Capability probe

What a build can do (version, filters, encoders, hardware decoders, xfade transitions, graph-file flag) comes from six short FFmpeg runs, made side by side (`media/caps.py`, `probe_caps`). The result is kept per user in `ffmpeg-caps.json` (in `%LOCALAPPDATA%\Video-Flow`, or `~/.local/share/video-flow`), keyed by the paths, sizes and modification times of `ffmpeg` and `ffprobe`: a launch with the same build runs no FFmpeg at all, and a new or replaced build (an install, another PATH) is probed once. A damaged or unwritable file only costs a probe. `GET /api/ffmpeg` looks for the binaries again each time and probes only when they changed (about 3 ms instead of 300 ms here).

## Pinned builds

`backend/videoflow/media/ffmpeg_install.py` pins one static build per platform, by URL and SHA-256:

| Platform | Build | Distributor | Licence |
|----------|-------|-------------|---------|
| Windows x64 | 7.1.1 full build (includes `flite` for the sample generator) | [gyan.dev](https://www.gyan.dev/ffmpeg/builds/) | GPL-3.0 |
| Linux x64 | 7.0.2 static | [John Van Sickle](https://johnvansickle.com/ffmpeg/) | GPL-3.0 |

No build is pinned for other systems (Windows ARM64, Linux ARM64): FFmpeg is installed manually there. The distributor builds the archive and provides its source code; Video-Flow installs it unchanged. Only `ffmpeg`, `ffprobe` and the archive's licence and readme files (`LICENSE` and `README.txt`, or `GPLv3.txt` and `readme.txt`) are copied into `tools/ffmpeg/`. If the downloaded archive does not match its checksum (for example because the distributor replaced it), nothing is installed. `scripts/install.sh` and `scripts/install.ps1` pin the same builds; a test checks that they agree.

## In the app

At start, when no usable FFmpeg is found, the FFmpeg window opens before the AI models window. It says why FFmpeg is needed, and shows the pinned build: version, distributor, licence, download size, source URL and the target folder. Nothing is downloaded until the user clicks **Download and install**; **Later** closes the window. During the download a progress bar and **Cancel** are shown; a failure (network, checksum, disk) is reported in the window. Once installed, the window shows the version and path found, and the app uses it at once (no restart). Without a pinned build, the window explains how to install FFmpeg manually.

Settings → FFmpeg opens the same window at any time to check the version in use.

API: `GET /api/ffmpeg` (status, pinned build, download job), `POST /api/ffmpeg/install`, `POST /api/ffmpeg/cancel`.

## In the install scripts

`scripts/install.sh` and `scripts/install.ps1` keep a local `tools/ffmpeg/` or a system FFmpeg when it is 6.1 or newer. Otherwise they print the same information (source, distributor, licence) and ask before downloading. `--yes` (`-Yes` in PowerShell) accepts without asking; without a terminal and without `--yes`, the download is skipped with instructions. `--no-ffmpeg` (`-NoFfmpeg`) skips the check. `VIDEOFLOW_FFMPEG_URL` and `VIDEOFLOW_FFMPEG_SHA256` select another archive; the checksum is always verified.

## Validation

- `tests/media/test_caps_cache.py`: one probe per build across launches, a new probe for a changed build or a damaged cache file.
- `tests/media/test_ffmpeg_install.py`: zip and tar.xz unpacking with licence files, checksum mismatch, platforms, scripts pinning the same builds.
- `tests/editor/test_api.py::test_ffmpeg_status_and_consented_install`: status, install job, no pinned build.
- Checked by hand on Linux x64: real download from the app window and from `scripts/install.sh`.
