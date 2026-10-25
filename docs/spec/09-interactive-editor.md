# 09. Interactive editor revision — 2026-10-25

This document supersedes conflicting UI, clip, import and editing rules in 02–08. The supplied wireframe is the reference: preview/editor above a transport timeline, with a branching clip flow below. No cloud hosting is required.

The accepted [desktop-shell revision](10-desktop-shell.md) supersedes this document's original browser-first launch and upload/copy behavior. Editing interactions below remain unchanged.

## Workspace

1. Preview and spatial editor: composite enabled video layers, highest layer on top; play enabled audio layers together. Select a clip for scale, crop and position handles. Shift breaks the aspect ratio; Alt moves opposite edges symmetrically. Position snaps to canvas center and sides (cropped picture bounds). Output menu lists landscape, portrait and square resolutions with ratios. Resolution changes preserve proportions and center the old canvas inside the new one using a uniform fit factor, including all clip positions, dimensions and crops.
2. Transport timeline: draggable cursor, beginning, −10 s, −1 s, −1 frame, play/pause, +1 frame, +1 s, +10 s, end. Ctrl+wheel zooms around the pointer's time, retaining that point under the pointer. Horizontal scrolling supports long edits. Frame arithmetic uses the project's rational rate.
3. Interactive clip flow: as many source clips and parallel alternatives/layers as needed, scrollable in both directions. Video is above its linked audio; a chain button detaches them. Linked partners move, split and trim together. Independent clips move and edit independently. Per-clip enable boxes control output; alternatives are ordinary layers and may be enabled simultaneously.

Uncovered time is compacted from the assembly. Authored empty clips are the exception and explicitly retain their duration (black/silence). Disabling an entire uncovered section removes its time; disabling one layer over another does not.

## Keyboard and focused editing

Space toggles playback at the cursor. Left/right step one frame; Shift steps one second; Ctrl steps ten seconds; Ctrl+Shift or Home/End goes to timeline bounds. Editable text inputs retain their normal keyboard behavior. Escape and double-clicking flow background leave clip focus. Double-click a clip to focus its range with two seconds of context on either side, clamped at project bounds; playback/navigation use that focused range until Escape.

Split at the cursor produces two independent segments; each segment retains its own linked video/audio pair when split while linked. Delete lifts selected content, replacing its occupied range with an explicit empty clip. Backspace removes it and ripples later clips left. Top trim handles ripple the assembly; bottom handles preserve total time by adding/extending neighboring empty clips. Extending requires available source frames. Both trim modes move linked partners together. Undo/redo operate on whole gestures, including linked changes.

On extension, bottom handles consume adjacent empty time first. Extending beyond that empty time is permitted up to the source boundary and ripples the remaining extension, including at the beginning/end of the assembly. Neighboring empty clips merge rather than accumulating separate placeholder blocks.

## Import and analysis

Files dropped on the flow (or picked with Import) open an analyse/skip choice. Process batch files sequentially; display filename, per-file progress and overall file number/count. Cancel one file or the batch, including subprocess/ML work. Failed files do not stop later imports. Successfully imported files remain after batch cancellation.

Use `<source stem>.json` beside the source, containing a version, source fingerprint, timecoded words (integer microseconds), summary and keywords. Read compatible existing analysis before loading models. Native drops and the native file picker reference the original file by path, without uploading or copying its contents into the bundle. Check the sidecar next to that original source, generating it there when analysis is requested and absent; read-only locations use the bundle-cache fallback specified in 10. The app never overwrites incompatible/unrelated JSON. Sidecar publication is atomic. Summaries/keywords use a local deterministic text fallback; transcription uses the existing real ASR engine. No pretend transcripts on failure.

Use transcript and keyword similarity to place matching clips at the same assembly position on different layers; otherwise append. Grouping is a suggestion the user can change. Silent files remain importable; they have empty transcripts. AI model downloads may be necessary on the first analysed import and are shown as an analysis phase.

## Data and implementation contract

The existing schema-v1 project supports an optional, versioned `editor` extension (unknown fields already round-trip). Once present it is authoritative for the interactive edit and resolved timeline; legacy beats remain readable. Each editor clip has an opaque id, asset id or explicit gap kind, source in/out frames at the project rate, assembly start frame, layer, enable state, optional link id, gain, and a video transform in output pixels. Only explicit gaps may have no asset. Validate source bounds, link pairs, unique ids, and finite transforms. Snapshot semantic `SetEditor` commands use the existing revision/inverse/history mechanism; the client owns session undo/redo.

The backend resolves this extension into the common resolved timeline so existing exports see the actual edit. OTIO uses separate tracks for overlapping layers and gaps for empty clips. EDL remains a V1-only handoff; layered output and transform limitations must be reported. The local API serves only the selected project media/proxies, authenticates per launch and validates Host/Origin. Native selections receive scoped file-import grants; optional browser typed-path imports remain restricted to configured roots. The React/Vite interface runs inside a PySide6/Qt WebEngine desktop window; normal launch opens that window rather than a browser tab. See 10 for host/API boundaries and lifecycle. No external service is needed for editing or analysis.

## Acceptance

Automated checks cover linked split/move/trim, source bounds, lift versus ripple delete, no implicit gaps, layer/enable resolution, resolution-fit transforms, cursor-anchored zoom and keyboard stepping; API checks cover revision conflicts, auth, sidecar reuse, sequential/cancellable imports and range serving. A desktop smoke test in Qt WebEngine uses generated local media to verify native path import without copying, preview, focus, split, undo and reload persistence; browser tests remain supplementary. Real ASR accuracy and real-editor export interoperability remain separate target-machine validations.
