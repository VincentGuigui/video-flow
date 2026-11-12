# Desktop runtime and platform qualification

Video-Flow uses PySide6 and Qt WebEngine to host the built React interface. Normal launch is `videoflow desktop` (or `videoflow` with no arguments). `videoflow serve` is an explicit browser diagnostic mode. `scripts/run.ps1` and `scripts/run.sh` launch the desktop application. Originals are referenced in place; only derived data is generated inside the project bundle. OTIOZ explicitly collects source media.

## Development

Install `uv sync --extra desktop --extra cpu` in `backend/`, then `npm install` and `npm run build` in `frontend/`. Run `videoflow desktop --project PATH.video-flow`. Native picks and drops use single-use, file-scoped grants; the browser renderer receives opaque handles, not arbitrary filesystem capabilities. Typed-path diagnostic imports retain configured-root restrictions. Browser uploads are disabled by default and are always disabled in the desktop host.

The selected Qt WebEngine build may lack H.264/AAC codecs. The frontend checks codec support and requests a cached VP9/Opus WebM playback proxy when needed. The existing H.264 SDR proxy remains the normalization stage for video. These are generated caches, never copies of original rushes. The renderer has no general local-file access and cannot navigate to privileged external pages.

Analysis checks the compatible source-adjacent JSON first, then fingerprint-keyed bundle cache. Successful analysis is cached before attempting the sidecar write. A read-only directory or unrelated existing JSON produces a warning identifying the cache; it does not require retranscription. Missing sources are shown as offline; native relinking verifies the original fingerprint and retains authored edits.

## Startup

The log line `Video-Flow startup (seconds since the process started): …` gives the time of each step of the last launch (see [desktop shell](../architecture/desktop-shell.md#startup)). Measured on Linux (warm disk cache, software rendering): window shown at 0.5 s, project shown at 1.2–1.35 s. What shortens it:

- The window opens with a loading screen before the backend is ready, while the backend imports and builds the API in its thread. Both need Python's global lock, so the total time hardly changes; the window shows about 0.4 s sooner.
- FFmpeg's capabilities are probed once per build ([FFmpeg capability probe](../architecture/projects-and-setup.md#capability-probe)), not at every launch.
- The packaged app ships compiled Python bytecode. A run from source compiles it at the first launch after an install or update (about 3.6 s on Linux), then reuses `__pycache__`.

## Qualification

Windows x64 / Python 3.13 / PySide6 6.12: development and standalone Qt WebEngine checks exercise local-file drop outside browser roots, scoped import without original copying, actual video decoding/playback, Space, focused linked splitting, undo, reload persistence and owned-backend shutdown. The standalone check also uses a Unicode/spaces source path. The tested wheel reports no H.264 support; WebM fallback is required. Run `scripts/desktop_smoke.py --media PATH --output .cache/desktop-qa` with the backend Python to reproduce, or `Video-Flow.exe desktop-check MEDIA_PATH OUTPUT_DIRECTORY` for the packaged check. Each records results and a screenshot. The development sample completed in approximately seven seconds, including import/proxy generation; this is a small synthetic-media check, not a multi-gigabyte benchmark or a claim of frame-perfect gapless playback or real-rush analysis accuracy.

Linux x86_64 and Windows ARM64 remain unqualified until the same native, media, driver and packaging tests run on those targets. Windows ARM64 requires confirmation of PySide6/Qt WebEngine wheels, Python compatibility and packaged playback. Do not infer ARM64 support from Windows x64 success. No alternative shell or Python-version change is implied.

## Packaging

Run `scripts\5-package.bat` or `scripts/dev.ps1 package` (Windows) or `scripts/dev.sh package` (Linux), or `just package`. It builds the frontend, then runs PyInstaller with the `desktop` extra and the `packaging` group added to the installed environment (the selected inference extra, and `whisper` / `qwen` when offered, must already be installed):

```text
uv run --project backend --inexact --extra desktop --group packaging python scripts/package_release.py
```

The executable embeds every Python module, so it is rebuilt only when Python code, installed packages, `assets/` or the spec change; the script fingerprints these inputs (`_internal/build-inputs.txt`) and, when they are unchanged, only copies the built interface into `_internal/frontend/dist` without running PyInstaller. `package --full` (or `5-package.bat --full`) forces a rebuild. Full builds are incremental too: PyInstaller keeps its dependency analysis in `.cache/pyinstaller/work` and reruns it only when Python code, installed packages or the spec change (it logs `Building because …`); otherwise a repackage takes seconds. The built interface is added after the analysis so a frontend change never triggers it. Delete `.cache/pyinstaller` to force a clean build. On Windows, excluding the repository folder from Microsoft Defender real-time scanning shortens builds that copy the large AI runtime libraries. Each package also places the menu shortcut script of the platform next to the executable (from `scripts/release/`): `Add Video-Flow to Start Menu.bat` creates `Video-Flow.lnk` in the current user's Start menu with the executable's icon; `add-video-flow-to-menu.sh` writes `~/.local/share/applications/video-flow.desktop`. `scripts/package_release.py` builds into `.cache/pyinstaller/` and then replaces only the executable and `_internal/` in `releases/Video-Flow`, so `models/`, `tools/`, `templates/`, `settings.json` and logs beside the executable survive a repackage.

### GitHub releases

The **Release** GitHub Action builds Windows x64 (DirectML) and Linux x64 (CPU) from one commit, packages the generated release folder into `Video-Flow-<version>-windows-x64.zip` and `Video-Flow-<version>-linux-x64.zip`, and publishes both with SHA-256 checksums. Run it manually from Actions, or push a matching version tag. It validates all version files and notes, waits for both packages, verifies artifacts, then creates the version tag if absent and publishes **Video-Flow <version>**. It refuses to reuse a tag from another commit. See [automated releases](github-releases.md) for usage and retry behavior. Runtime tests/qualification are separate from this packaging workflow. Windows builds restore DirectML after Whisper's CPU ONNX dependency is installed.

The one-folder release includes the Python runtime, Qt WebEngine resources, OTIO adapter data and built frontend. End users do not need Node, Vite, uv or a frontend development server. FFmpeg/ffprobe are separately provisioned: when none is found, the app offers at start to download a pinned, checksum-verified build into `tools/ffmpeg/` beside the executable (see [FFmpeg setup](../features/getting-started/ffmpeg-setup.md)); a build put there or on PATH is used as well. Model downloads remain governed by the pinned engine manifest. Weights always live in `models/` beside the executable (repository `models/` in development); `VIDEOFLOW_MODELS_DIR` is set to that directory, and external overrides are ignored. Settings lists missing, obsolete and up-to-date models, with explicit download/update and cancellation. No model download begins merely by opening the editor. Signatures, installers, updates and distribution hardening are later release work. Packaging success alone does not qualify playback on another platform.

The Windows recipe pins the bundled MSVC family to Qt's working runtime and excludes unsuffixed ICU DLLs from unrelated SDKs on PATH. Qt uses Windows' system ICU; accidentally bundling a Poppler/Conda ICU causes a missing-procedure failure even when the development application works. Rebuild only after frontend assets are stable. Packaged OTIO, EDL and paper-edit exports have also been checked; real-model inference/downloads and external-editor interoperability still need dedicated release validation.

## Licence notices

- Video-Flow's Python/React code: MIT, as declared in the project metadata.
- PySide6/Shiboken and Qt libraries: LGPL-3.0/GPL/commercial terms according to the included Qt component; preserve the wheel's licence files and Qt's third-party notices when redistributing. Qt WebEngine includes Chromium and its third-party licences. This development packaging recipe is not a substitute for a distributor's licence review.
- React, Vite, Zustand and Lucide: MIT; retain package licence notices in releases.
- FFmpeg licensing depends on the selected external build (the pinned builds are GPL-3.0). It is not embedded by this recipe; the app downloads it only on the user's request, unchanged, with its licence files.
- AI model licences and attribution remain in `docs/reference/dependencies.md` and `engines/manifest.toml`; models are not included in the application bundle by default.

## Settings and AI engines

The settings panel offers Parakeet or Whisper tiny transcription, a preferred speech device, deterministic or Qwen summaries/keywords, import-analysis defaults and render-quality/audio-normalization defaults. Application preferences persist in `settings.json` beside the executable (repository root in development). The selected installation directory must be writable; failed writes/downloads are reported rather than redirected into AppData.

Model status compares cached files against the immutable revisions shipped in the app manifest. Obsolete means another revision is installed, not that a live Hub search found a newer release. Update obtains the supported revision. Download workers are cancellable; incomplete downloads remain resumable and never count as installed. Opening Settings or choosing an engine does not approve a download. Analysed imports reuse compatible sidecars first, then pause for download approval if required weights are absent. Import-only remains available.

Qwen uses [Qwen2.5-0.5B-Instruct](https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct) through local Transformers/PyTorch CPU inference in the owned worker. It loads pinned local safetensors without remote code or network inference. Summary input is limited to the first and last 1400 tokens for transcripts over 2800 tokens; the analysis JSON records that scope. Invalid generated JSON is reported as an analysis failure. Existing compatible sidecars retain their original summaries. Speech acceleration preferences apply to ASR/VAD; Qwen currently uses CPU.

The expanded native check (`--features`) additionally exercises real Qt zoom, the project home screen, decoded blurred backgrounds, MP4 rendering and Save as. MP4 uses original media and validates frame count, dimensions, rational frame rate and audio duration before publishing. Transparent clip backgrounds reveal lower layers, or black in the final H.264 MP4. Legacy transition/fade rendering remains unsupported and fails explicitly rather than silently dropping effects.

The editor now uses one shared assembly time axis. The flow has no separate ruler or cursor. Select an unlinked clip and use Link audio / Link video in properties to choose an opposite-kind clip with matching assembly start and duration; source offsets may differ. Audio edge trims retain time without adding clip placeholders. Native `desktop-check --features` also verifies this behavior and live transform input.

## Inference dependencies

These are Python packages, separate from model weights in `models/`: installing them never downloads weights, and existing weights need no new download.

- The `desktop` extra installs Qwen's PyTorch, Transformers and safetensors runtimes. Whisper is an optional extra. One accelerator extra (`cpu`, `openvino`, `cuda`, `directml`, `qnn`) provides the ONNX runtime for speech, VAD and similarity.
- A source install is repaired with `uv sync --extra desktop --extra cpu` in `backend/` (replace `cpu` with the chosen accelerator), then a restart. When Qwen's runtime is incomplete, analysis says how to restore it or to use deterministic summaries.
- The **Install components** window ([AI models and components](../features/getting-started/ai-models.md)) checks the selected runtimes as well as the weights. In a source desktop build it installs missing packages into its Python environment with uv (progress, cancellation, errors, restart notice); browser diagnostic mode cannot install packages; a frozen build includes its runtimes and, if one is missing, asks for a reinstall instead of running a package manager.
- When CUDA is advertised, startup preloads the matching NVIDIA libraries and runs a tiny ONNX session; a silent CPU fallback is reported as unavailable acceleration. **Install CUDA libraries** installs the CUDA/cuDNN extras of the installed ONNX GPU version; **Use CPU** saves the speech device preference. NVIDIA drivers and, on Windows, the MSVC runtime are system prerequisites. Checks are cached for the process: restart after installing.
- Whisper's CPU ONNX dependency can replace a GPU or DirectML wheel: the in-app Whisper repair installs its engine, CTranslate2 and AV packages without replacing the existing ONNX provider.
- Release CI installs Qwen explicitly, and the desktop build fails when an inference runtime is missing instead of publishing an executable with missing hidden imports.

## CUDA release libraries

When the build environment's ONNX Runtime advertises CUDA, `scripts/desktop.spec` collects the installed GPU wheel's `[cuda,cudnn]` NVIDIA requirements recursively through `desktop/cuda_bundle.py`. It validates installed versions, bundles their native DLLs/shared libraries in `_internal/cuda/`, and retains their distribution metadata and licence notices. If dependencies are missing, packaging stops: install `onnxruntime-gpu[cuda,cudnn]` at the same version as the selected GPU wheel before rebuilding. This is separate from model weights and does not download models. CPU/DirectML release builds skip CUDA library collection.

The frozen runtime preloads that specific directory; Windows also retains its DLL search handle for cuDNN's dynamically loaded engines. Drivers remain system dependencies. Validate from the new release folder using `Video-Flow.exe components-check OUTPUT.json` (Linux: `./Video-Flow components-check OUTPUT.json`), with development CUDA/Python paths removed. The report must identify the expected version and a working CUDA inference session. End users must keep the complete release folder including `_internal/`.
