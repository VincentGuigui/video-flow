# Desktop runtime and platform qualification

Video-Flow uses PySide6 and Qt WebEngine to host the built React interface. Normal launch is `videoflow desktop` (or `videoflow` with no arguments). `videoflow serve` is an explicit browser diagnostic mode. `scripts/run.ps1` and `scripts/run.sh` launch the desktop application. Originals are referenced in place; only derived data is generated inside the project bundle. OTIOZ explicitly collects source media.

## Development

Install `uv sync --extra desktop --extra cpu` in `backend/`, then `npm install` and `npm run build` in `frontend/`. Run `videoflow desktop --project PATH.videoflow`. Native picks and drops use single-use, file-scoped grants; the browser renderer receives opaque handles, not arbitrary filesystem capabilities. Typed-path diagnostic imports retain configured-root restrictions. Browser uploads are disabled by default and are always disabled in the desktop host.

The selected Qt WebEngine build may lack H.264/AAC codecs. The frontend checks codec support and requests a cached VP9/Opus WebM playback proxy when needed. The existing H.264 SDR proxy remains the normalization stage for video. These are generated caches, never copies of original rushes. The renderer has no general local-file access and cannot navigate to privileged external pages.

Analysis checks the compatible source-adjacent JSON first, then fingerprint-keyed bundle cache. Successful analysis is cached before attempting the sidecar write. A read-only directory or unrelated existing JSON produces a warning identifying the cache; it does not require retranscription. Missing sources are shown as offline; native relinking verifies the original fingerprint and retains authored edits.

## Qualification

Windows x64 / Python 3.13 / PySide6 6.12: development and standalone Qt WebEngine checks exercise local-file drop outside browser roots, scoped import without original copying, actual video decoding/playback, Space, focused linked splitting, undo, reload persistence and owned-backend shutdown. The standalone check also uses a Unicode/spaces source path. The tested wheel reports no H.264 support; WebM fallback is required. Run `scripts/desktop_smoke.py --media PATH --output .cache/desktop-qa` with the backend Python to reproduce, or `Video-Flow.exe desktop-check MEDIA_PATH OUTPUT_DIRECTORY` for the packaged check. Each records results and a screenshot. The development sample completed in approximately seven seconds, including import/proxy generation; this is a small synthetic-media check, not a multi-gigabyte benchmark or a claim of frame-perfect gapless playback or real-rush analysis accuracy.

Linux x86_64 and Windows ARM64 remain unqualified until the same native, media, driver and packaging tests run on those targets. Windows ARM64 requires confirmation of PySide6/Qt WebEngine wheels, Python compatibility and packaged playback. Do not infer ARM64 support from Windows x64 success. No alternative shell or Python-version change is implied.

## Packaging

Build frontend assets, install the `packaging` dependency group alongside `desktop` and the selected inference extra, then run:

```text
pyinstaller --noconfirm --distpath tools/release --workpath .cache/pyinstaller scripts/desktop.spec
```

The one-folder release includes the Python runtime, Qt WebEngine resources, OTIO adapter data and built frontend. End users do not need Node, Vite, uv or a frontend development server. FFmpeg/ffprobe are separately provisioned: put a supported build in `tools/ffmpeg/` beside the executable, or on PATH. Model downloads remain governed by the pinned engine manifest. Signatures, installers, updates and distribution hardening are later release work. Packaging success alone does not qualify playback on another platform.

The Windows recipe pins the bundled MSVC family to Qt's working runtime and excludes unsuffixed ICU DLLs from unrelated SDKs on PATH. Qt uses Windows' system ICU; accidentally bundling a Poppler/Conda ICU causes a missing-procedure failure even when the development application works. Rebuild only after frontend assets are stable. Packaged OTIO, EDL and paper-edit exports have also been checked; real-model inference/downloads and external-editor interoperability still need dedicated release validation.

## Licence notices

- Video-Flow's Python/React code: MIT, as declared in the project metadata.
- PySide6/Shiboken and Qt libraries: LGPL-3.0/GPL/commercial terms according to the included Qt component; preserve the wheel's licence files and Qt's third-party notices when redistributing. Qt WebEngine includes Chromium and its third-party licences. This development packaging recipe is not a substitute for a distributor's licence review.
- React, Vite, Zustand and Lucide: MIT; retain package licence notices in releases.
- FFmpeg licensing depends on the selected external build (the full GPL build includes GPL components). It is not silently embedded by this recipe.
- AI model licences and attribution remain in `docs/dependencies.md` and `engines/manifest.toml`; models are not included in the application bundle by default.
