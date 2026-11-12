# Release notes

Changes per version, newest first, written for users. The GitHub release of a version gathers the entries of every version since the previous GitHub release ([automated releases](reference/github-releases.md)).

Format (checked by the release workflow, `scripts/release_artifacts.py`):

- One section per version: `## <version> — <date>`, the version set in `backend/pyproject.toml`.
- One line per change: `- <TYPE>: <short, explicit sentence for users>`, with `<TYPE>` one of:
  - `FEATURE`: something new the user can do;
  - `IMPROVEMENT`: something existing that works better;
  - `FIX`: a bug fixed;
  - `DEV`: infrastructure or technical work only (left out of GitHub release notes).

## 0.37.0 — 2026-11-12

- FEATURE: Video-Flow offers new versions at start and updates itself from GitHub, keeping your models, FFmpeg and settings; a version can be skipped, and Settings checks on request.
- FIX: Changing settings or removing a model no longer starts a second preview queue.

## 0.36.0 — 2026-11-12

- FEATURE: Search what is said in the edit (Ctrl + F): matching clips and occurrences are marked in the clip flow, and Enter or the arrows move the cursor from one occurrence to the next.
- DEV: The unused H.264 proxy encoder is removed; its size, frame-rate, tone-mapping and rotation tests now check the WebM previews.

## 0.35.0 — 2026-11-12

- IMPROVEMENT: Imported videos are usable at once: the preview shows one picture per second with the real sound until the smooth preview video is ready.
- IMPROVEMENT: Preview videos are made in the background, one at a time and at low priority, so the timeline stays fluid; the media list shows their progress.

## 0.34.0 — 2026-11-08

- DEV: GitHub release notes follow a fixed template and gather the changes of every version since the previous release.

## 0.33.0 — 2026-11-08

- DEV: Releases are built for Windows and Linux, checked, tagged and published by a GitHub workflow.
- FIX: Release builds no longer fail on a broken frontend dependency list.

## 0.32.0 — 2026-11-08

- IMPROVEMENT: Range guides line up across the merged timeline and flow.

## 0.31.0 — 2026-11-08

- FIX: Transcript corrections are kept when the media folder is read-only.

## 0.30.0 — 2026-11-08

- IMPROVEMENT: A dissolve holds the edge frame when a clip has no more media beyond the cut.

## 0.29.0 — 2026-11-08

- IMPROVEMENT: Compare takes is in the flow toolbar when takes are stacked.

## 0.28.0 — 2026-11-08

- IMPROVEMENT: The duplicate Delete range button is gone from clip properties.

## 0.27.0 — 2026-11-08

- IMPROVEMENT: Trim to range and auto-trim silence are in the flow toolbar.

## 0.26.0 — 2026-11-08

- IMPROVEMENT: Delete and Backspace remove the selected range first, then whole clips.

## 0.25.0 — 2026-11-08

- FEATURE: Timeline and clip flow are merged, with one cursor and range across both.

## 0.24.0 — 2026-11-08

- IMPROVEMENT: Clip actions and the clip count sit below the flow.

## 0.23.0 — 2026-11-08

- IMPROVEMENT: Playback controls sit above the video preview.

## 0.22.0 — 2026-11-08

- IMPROVEMENT: Output resolution is set in Project properties.

## 0.21.0 — 2026-11-08

- FEATURE: Transcription can be edited word by word, and the corrections are saved.

## 0.20.0 — 2026-11-08

- FEATURE: Selecting text in the transcript selects the matching range on the timeline.

## 0.19.0 — 2026-11-08

- FEATURE: Hovering a medium for two seconds shows its topics.

## 0.18.0 — 2026-11-08

- IMPROVEMENT: Double-clicking a clip in the timeline focuses its edit.

## 0.17.0 — 2026-11-08

- FIX: GPU (CUDA) analysis keeps working after moving the app to another folder.
- DEV: Packaging refuses missing or incompatible CUDA libraries and keeps their licences.

## 0.16.0 — 2026-11-08

- FIX: The status bar shows the real app version.

## 0.15.0 — 2026-11-08

- FEATURE: The setup window finds missing AI components and offers to install them, or to use the CPU.
- IMPROVEMENT: GPU readiness is checked with a real test before analysis.
- FIX: Installing Whisper no longer replaces the GPU runtime.

## 0.14.0 — 2026-11-08

- FIX: Qwen summaries no longer fail with a missing PyTorch module.
- DEV: Release builds include the Qwen and Whisper runtimes and refuse to package without them.

## 0.13.0 — 2026-11-04

- FEATURE: Hovering a clip in the flow shows a one-line description; audio clips show the same text as their video.
- FIX: Analysing a medium again refreshes its transcript and tooltips at once.

## 0.12.0 — 2026-11-01

- IMPROVEMENT: The window opens at once with a loading screen, and FFmpeg is no longer probed at every start.
- FIX: The desktop app no longer crashes at start on Linux.
- DEV: The log records how long each step of the start takes.

## 0.11.0 — 2026-11-01

- FEATURE: Keyframes animate a video clip's position, size, rotation, crop and opacity (Animation tab, K).
- IMPROVEMENT: Keyframes replace zoom & pan; zooms of earlier projects are ignored.

## 0.10.0 — 2026-11-01

- FEATURE: Freeze frame (F) inserts a 3 s still of the frame at the cursor.

## 0.9.0 — 2026-11-01

- FEATURE: Still images can be imported and used as clips (3 s by default, any length).

## 0.8.0 — 2026-11-01

- FEATURE: Add clip effects and transitions from the Effects tab, or by clicking a cut in the flow.

## 0.7.0 — 2026-11-01

- IMPROVEMENT: The properties panel can be resized, made tall, or unpinned to float over the editor.

## 0.6.0 — 2026-11-01

- IMPROVEMENT: Right-click shows only the app's own menus.

## 0.5.0 — 2026-11-01

- FEATURE: FFmpeg download is proposed when the app starts (and in Settings), only with your consent.
- IMPROVEMENT: The install scripts ask before downloading FFmpeg and always verify it.

## 0.4.0 — 2026-11-01

- DEV: GitHub releases for Windows and Linux are built by a workflow.
- IMPROVEMENT: Analysing a medium again stacks it over the retake it matches.
- FIX: SRT and paper edit leave out words said inside muted ranges.

## 0.3.0 — 2026-11-01

- FEATURE: AI model downloads are proposed when the app starts (and in Settings), with sizes, update and remove.
- FEATURE: A script next to the app adds Video-Flow to the Start menu (Windows) or the applications menu (Linux).

## 0.2.0 — 2026-11-01

- FEATURE: Desktop editor that imports media in place, with a project home, save and save as.
- FEATURE: Local transcription, summary and topics; AI runs on the NPU, then the GPU, then the CPU.
- FEATURE: Retakes are stacked on import and can be compared side by side.
- FEATURE: Editing with a layered clip flow, linked audio and video, split, trim, undo, range and transcript-driven trimming.
- FEATURE: Fades, speed, mute ranges, ducking under speech, titles and lower thirds.
- FEATURE: Projects live next to your media and can be moved with them.
- FEATURE: MP4 render, and exports to OTIO, EDL, SRT, paper edit and Camtasia.
