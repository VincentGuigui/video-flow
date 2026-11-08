# Roadmap

Snapshot of what is built and what comes next. Update it with every feature. History lives in [decisions/](decisions/).

## Built

- **Desktop app:** status bar reports the running application version; CUDA releases bundle compatible native libraries; PySide6 / Qt WebEngine window hosting the React editor; native file and folder dialogs and drops; only the app's own context menus; window shown at once with a loading screen, startup timeline in the log; originals referenced in place, relink when offline. See [desktop shell](architecture/desktop-shell.md).
- **Clip tooltip:** hovering a clip in the flow shows its one-line description from the analysis (audio: the same as its video). See [clip tooltip](features/clip-tooltip.md).
- **Properties panel:** resizable, half or tall height, pinned or floating (folds into a strip when the pointer leaves). See [properties panel](features/properties-panel.md).
- **FFmpeg setup:** FFmpeg window at start and in Settings; download of a pinned, checksum-verified build into `tools/ffmpeg/` only on the user's consent, also in the install scripts. See [FFmpeg setup](features/ffmpeg-setup.md).
- **Projects:** `<name>.video-flow` folders in the working folder with relative media paths (the whole folder can be moved), recent list, home page, save as, rename; application cache outside projects with size, open and clear in Settings. See [projects](features/projects.md).
- **Still images and freeze frames:** PNG, JPEG, WebP, BMP and TIFF in the media library; Freeze (F) inserts a 3 s still of the frame at the cursor, splitting the clip; still clips trim freely, dissolve, render and export (Camtasia `IMFile`, OTIO `FreezeFrame`, EDL M2). See [still images](features/still-images.md).
- **Project media:** context menu with Info (location, analysis, transcript) and re-analysis. See [project media](features/media-library.md).
- **Import and analysis:** startup component checks, explicit dependency installation, CUDA initialization check and CPU option; desktop installs include Qwen, packaging rejects missing inference runtimes; probe, playback proxies, thumbnails, waveforms; VAD, transcription (Parakeet TDT or Whisper), summary, keywords and topic sections; reusable analysis sidecars; models downloaded only on request; NPU → GPU → CPU device choice. See [interactive editor](features/interactive-editor.md), [transcript panel](features/transcript-panel.md).
- **Retakes:** retakes stacked on import by sentence similarity; compare takes side by side and pick one. See [retake grouping](features/retake-grouping.md), [compare takes](features/compare-takes.md).
- **Editing:** layered clip flow and timeline, linked video/audio, split, lift, ripple delete, trim modes, focus, undo/redo, transforms and backgrounds, timeline range and range playback, transcript-driven trim and delete, auto-trim silence, detach and restore audio, workspace zones with select all and delete. See [unified timeline](features/unified-timeline.md), [range and trim](features/range-and-trim.md), [audio tracks](features/audio-tracks.md), [workspace zones](features/workspace-zones.md).
- **Finishing:** Effects tab with transition cards (opened from cut markers in the flow and transition bands in the timeline) and effect cards with Add effect; cross dissolve and dips, edge fades, speed, keyframed transforms (position, size, rotation, crop, opacity), mute ranges, ducking under speech, titles and lower thirds. See [transitions](features/transitions.md), [clip effects](features/clip-effects.md), [keyframes](features/keyframes.md).
- **Output:** MP4 render with hardware encoders when available and loudness normalisation; OTIO, OTIOZ, EDL, SRT, paper edit and Camtasia 2023.4+ exports. See [render and export](architecture/render-export.md), [Camtasia export](features/camtasia-export.md).

## Next

- Confirm the Camtasia export in Camtasia itself (opening, fades, linked audio, titles).
- Measure retake grouping and transcription accuracy on real rushes, and tune thresholds.
- Qualify NPU execution providers (OpenVINO, QNN, VitisAI) and GPU encoders on target Windows and Linux machines; Windows ARM64 qualification gate.
- Release packaging and installer hardening for the desktop build.

## Later

- FCPXML and FCP7 XML export; OTIO re-import; interoperability checks in Resolve, Premiere and Final Cut Pro.
- Sync groups (multicam) and replacing a take's audio with another take's audio.
- Comping (ranges from several takes of one beat) and script-guided grouping.
- Extended transition catalog (wipes, slides) and subtitle burn-in.
- B-roll suggestions, vertical reframing, YouTube chapters from topics.
- French interface.

## Open risks

| Risk | Mitigation |
|------|------------|
| Grouping is less accurate on non-speech footage | Manual stacking and moving; visual features from the analysis pipeline |
| Phone footage quirks (VFR, HDR, rotation) | Proxies for preview, normalisation and tone mapping in the render |
| Camtasia format changes between versions | Template-driven writer: a project saved by the user's version provides the structures |
| Scope creep towards a full editor | Handoff to other editors through OTIO and Camtasia for advanced finishing |

Additional built editor interactions:

- Double-click assembly clips to focus their edit

- Show transcribed media topics after two seconds of hover

- Map transcript text selections onto the timeline range

- Correct transcript words in place and persist analysis JSON

- Set output resolution from Project properties

- Place playback controls above the video preview

- Place clip actions and clip count below the flow

- Merge timeline and clip flow with continuous cursor and range guides

- Delete or ripple the selected range before falling back to whole clips

- Move range trimming and silence trimming into the flow toolbar

- Remove the redundant Delete range action from clip properties

- Show Compare takes in the flow toolbar for parallel takes
