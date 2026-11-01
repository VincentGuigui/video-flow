# 10. Desktop shell and direct local media access — 2026-10-25

Status: accepted architecture revision. This document supersedes conflicting browser-first, upload/copy, pywebview and optional-desktop-packaging decisions in 01–09. It specifies intended behavior; it does not claim that the desktop shell has been implemented or validated.

## Decision

Video-Flow is a desktop application using **PySide6 with Qt WebEngine** to host the existing **React/Vite interface**. **Python/FastAPI, FFmpeg and the inference workers** retain their processing responsibilities. The three-part workspace and editing behavior in 09 remain unchanged.

The normal launch opens an application window, with no separate browser tab. A browser mode may remain available explicitly for development and diagnostics. Qt is the chosen desktop shell; pywebview, Tauri and Electron are not parallel implementation targets.

This choice preserves the interactive frontend while providing native file dialogs, local-path drag-and-drop and desktop lifecycle management. It does not make FFmpeg or inference intrinsically faster; the import efficiency comes from avoiding unnecessary transfers and copies.

## Media import: reference originals in place

- Dropping files from the operating system onto the flow, or using the native Import dialog, supplies their local filesystem paths through the desktop host. The host forwards path references to the existing import queue. No video bytes are uploaded, base64-encoded, sent through the JavaScript bridge or copied into the bundle during normal import.
- Qt handles local file URLs and path decoding, including spaces, Unicode, Windows drive paths and supported network locations. The host accepts actual files, checks media types and obtains canonical paths. Remote HTTP URLs are not treated as local-file imports.
- Importing several files retains the sequential processing, analyse/skip choice, per-file and global progress, cancellation and similarity grouping defined in 09. Referencing a file is quick; probing, hashing, proxy generation and optional analysis can still take time and must report their own progress.
- Original video and audio files remain unmodified at their selected locations. Project decisions, proxies, thumbnails, waveforms and working caches live in the project bundle. Re-importing known content reuses the existing asset and valid caches.
- Copying originals is an explicit **Collect media / portable project** operation, never an implicit cost of drag-and-drop. OTIOZ remains an explicit media-bundling export and may copy media for that purpose.
- Persist absolute source paths plus relative relinking hints where possible. Reopening a project must not require re-import or copying. If files are moved, renamed, deleted or temporarily unavailable, mark them offline and offer a native relink dialog; retain edits and never silently substitute another file.

## Analysis sidecars

The source-adjacent `<source stem>.json` contract from 09 remains in force: check for compatible timecoded transcription, summary, keywords and source fingerprint before loading speech models. Write a newly requested sidecar atomically next to the original source, without overwriting unrelated or incompatible JSON. Source media itself is never rewritten.

For a read-only source folder, keep the analysis in the bundle's analysis cache, associated with the source fingerprint, and report its location. Check that cache on subsequent imports so a failed sidecar write does not force retranscription. A later explicit action may write the sidecar next to the source when the folder becomes writable. The UI must distinguish analysis failure from successful analysis whose sidecar could not be saved beside the source.

## Host, frontend and backend boundaries

The PySide6 host owns application startup/shutdown, the native window, file dialogs, OS drag-and-drop and the narrow desktop bridge. React owns the existing workspace, timeline interactions and client-side editor state. Python services own project commands, persistence, import, analysis, rendering and exports.

Serve the built React assets from the authenticated loopback application origin within Qt WebEngine. FastAPI also serves project media/proxies with range support. HTTP range reads of a local proxy or source are permitted; a loopback playback stream is distinct from uploading and duplicating an imported file. Browser codec limitations still apply to Qt WebEngine: use the existing H.264 SDR proxy path where needed rather than promising native decoding of every camera format.

Use a narrow bridge, such as Qt WebChannel, for native operations and import events. Pass structured metadata and opaque import handles or asset IDs, not media contents or arbitrary executable requests. The host binds a native user selection to the selected files; the backend resolves the grant. Do not expose a general filesystem-read, filesystem-write or shell-execution bridge.

Preserve loopback binding, per-launch authentication, Host/Origin validation and project-scoped media serving. Native file selection/drop grants import access only to those files and their required sidecars; it must not grant the renderer unrestricted access to a drive or directory tree. Typed-path imports in optional browser mode retain configured-root restrictions. Native selection must work outside previously configured roots through the host's scoped grant, without requiring manual allowlist editing.

Only the trusted local editor origin may use the desktop bridge. Block navigation of the editor view to external pages; open intentional external links outside the privileged view. Do not disable web security or enable general local-file access as a workaround.

The desktop host starts the backend and waits until it is ready before loading the editor. It also coordinates shutdown of its owned backend, FFmpeg jobs and inference workers, without leaving orphan processes. Existing revision checks, command inverses and atomic saves remain the editing/persistence contract. Node/Vite are build-time tools; end users must not need a development server, Node or `uv` to run a packaged release.

## Implementation order and platform gates

1. Add the PySide6/Qt WebEngine host, trusted-origin bridge, native path drop and file dialog, and application lifecycle. Reuse the existing React frontend and Python services; no rewrite of the interface into Qt widgets is required.
2. Connect native selections to path-based imports with scoped grants. Keep browser byte-upload routes only as an explicit development/compatibility path, outside the normal desktop import flow.
3. Integrate source-adjacent sidecar reuse, read-only-folder fallback, offline-media status and relinking. Preserve sequential import and cancellation semantics.
4. Validate playback, hardware acceleration and interaction behavior inside Qt WebEngine on target machines. Browser-only tests do not establish desktop behavior.
5. Package the application with its required Python/Qt components, frontend assets and backend resources. Include dependency/licence notices and document separately provisioned FFmpeg/models as appropriate to the release.

Windows 11 x64 and Linux x86_64 remain release targets. Windows ARM64/Snapdragon remains a target requiring qualification: verify PySide6/Qt WebEngine availability, Python compatibility, packaging and media playback before claiming support. Do not silently change the Python version or substitute another desktop framework if this gate fails; document the specific blocker for a separate architecture decision. Desktop startup and native imports belong in the editor foundation, rather than being deferred to optional Phase 3 packaging. Installer/release hardening can remain a later milestone.

## Acceptance checks

- A normal launch opens the editor in a native desktop window, with no browser tab or frontend development server. Closing it terminates its owned services cleanly.
- OS file drop and the native picker import a multi-gigabyte local file by path. No original-media copy appears in the bundle and no request uploads the original contents. Generated proxies/caches are allowed and identified separately.
- Test Unicode/spaces, paths outside configured browser roots, multiple files, cancellation and supported network/read-only locations. The renderer cannot turn an import grant into arbitrary file access.
- An existing compatible sidecar skips transcription. A read-only source can reuse bundle-cached analysis without failing the whole import or retranscribing on reopening.
- Original source hashes stay unchanged. Saving/reopening preserves edits and source references; missing media becomes offline and can be relinked without losing trims or links.
- Verify the preview, layered audio/video, keyboard shortcuts, cursor-centred zoom, linked edits and transforms from 09 in the actual Qt WebEngine window. Measure responsiveness with many clips; record actual import/proxy/analysis timings rather than claiming instantaneous processing.
- Existing headless CLI and export tests continue to pass. Packaged builds are tested separately on each supported platform, including codec/proxy playback and required Qt runtime resources.
