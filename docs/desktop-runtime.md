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

Build frontend assets, install the `packaging` dependency group alongside `desktop` and the selected inference extra, plus `whisper` and `qwen` when those engines are offered, then run:

```text
pyinstaller --noconfirm --distpath releases --workpath .cache/pyinstaller scripts/desktop.spec
```

The one-folder release includes the Python runtime, Qt WebEngine resources, OTIO adapter data and built frontend. End users do not need Node, Vite, uv or a frontend development server. FFmpeg/ffprobe are separately provisioned: put a supported build in `tools/ffmpeg/` beside the executable, or on PATH. Model downloads remain governed by the pinned engine manifest. Weights always live in `models/` beside the executable (repository `models/` in development); `VIDEOFLOW_MODELS_DIR` is set to that directory, and external overrides are ignored. Settings lists missing, obsolete and up-to-date models, with explicit download/update and cancellation. No model download begins merely by opening the editor. Signatures, installers, updates and distribution hardening are later release work. Packaging success alone does not qualify playback on another platform.

The Windows recipe pins the bundled MSVC family to Qt's working runtime and excludes unsuffixed ICU DLLs from unrelated SDKs on PATH. Qt uses Windows' system ICU; accidentally bundling a Poppler/Conda ICU causes a missing-procedure failure even when the development application works. Rebuild only after frontend assets are stable. Packaged OTIO, EDL and paper-edit exports have also been checked; real-model inference/downloads and external-editor interoperability still need dedicated release validation.

## Licence notices

- Video-Flow's Python/React code: MIT, as declared in the project metadata.
- PySide6/Shiboken and Qt libraries: LGPL-3.0/GPL/commercial terms according to the included Qt component; preserve the wheel's licence files and Qt's third-party notices when redistributing. Qt WebEngine includes Chromium and its third-party licences. This development packaging recipe is not a substitute for a distributor's licence review.
- React, Vite, Zustand and Lucide: MIT; retain package licence notices in releases.
- FFmpeg licensing depends on the selected external build (the full GPL build includes GPL components). It is not silently embedded by this recipe.
- AI model licences and attribution remain in `docs/dependencies.md` and `engines/manifest.toml`; models are not included in the application bundle by default.

## Settings and AI engines

The settings panel offers Parakeet or Whisper tiny transcription, a preferred speech device, deterministic or Qwen summaries/keywords, import-analysis defaults and render-quality/audio-normalization defaults. Application preferences persist in `settings.json` beside the executable (repository root in development). The selected installation directory must be writable; failed writes/downloads are reported rather than redirected into AppData.

Model status compares cached files against the immutable revisions shipped in the app manifest. Obsolete means another revision is installed, not that a live Hub search found a newer release. Update obtains the supported revision. Download workers are cancellable; incomplete downloads remain resumable and never count as installed. Opening Settings or choosing an engine does not approve a download. Analysed imports reuse compatible sidecars first, then pause for download approval if required weights are absent. Import-only remains available.

Qwen uses [Qwen2.5-0.5B-Instruct](https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct) through local Transformers/PyTorch CPU inference in the owned worker. It loads pinned local safetensors without remote code or network inference. Summary input is limited to the first and last 1400 tokens for transcripts over 2800 tokens; the analysis JSON records that scope. Invalid generated JSON is reported as an analysis failure. Existing compatible sidecars retain their original summaries. Speech acceleration preferences apply to ASR/VAD; Qwen currently uses CPU.

The expanded native check (`--features`) additionally exercises real Qt zoom, the project home screen, decoded blurred backgrounds, MP4 rendering and Save as. MP4 uses original media and validates frame count, dimensions, rational frame rate and audio duration before publishing. Transparent clip backgrounds reveal lower layers, or black in the final H.264 MP4. Legacy transition/fade rendering remains unsupported and fails explicitly rather than silently dropping effects.

The editor now uses one shared assembly time axis. The flow has no separate ruler or cursor. Select an unlinked clip and use Link audio / Link video in properties to choose an opposite-kind clip with matching assembly start and duration; source offsets may differ. Audio edge trims retain time without adding clip placeholders. Native `desktop-check --features` also verifies this behavior and live transform input.
