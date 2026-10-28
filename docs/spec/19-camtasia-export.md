# 19. Camtasia export — 2026-10-28

This revision implements EXP-06 for Windows and supersedes 06 §8.3 where they differ. Targets Camtasia 2023.4 and later on Windows (the `.tscproj` format version 7.0 opens in newer releases). The media pack fallback and `.cmproj` (macOS) are not implemented.

## Template-driven writer

`.tscproj` is undocumented JSON. The writer (`exporters/camtasia.py`) clones structures from a template and fills them from the edit:

- Template: `templates/camtasia.tscproj` in the application folder if present (any project saved by the user's Camtasia), or `--camtasia-template PATH` on the CLI; otherwise the built-in default, which reproduces the structures of a real Camtasia 2023.4.3 project (UnifiedMedia, VMFile, AMFile, Fade transition, source-bin entries, track attributes, caption attributes) with neutral values.
- Cloned from the template: top-level settings and version, UnifiedMedia, VMFile, AMFile, transition objects by name, the first track and track-attribute objects, and a video source-bin entry with its source tracks. A missing structure falls back to the built-in one with a warning.
- Never copied from the template: its media, source bin, tracks and private project metadata (autosave path, thumbnail); only `CanvasZoom`, `Fit`, `Language` and `ProfileName` are kept.

## Mapping

| Edit | Camtasia |
|------|----------|
| Video lane (bottom-up) | One track per lane, in lane order; independent audio lanes follow |
| Linked video + audio | `UnifiedMedia` with inner `VMFile` and `AMFile` |
| Unlinked video / audio | `VMFile` / `AMFile` |
| Clip start, duration, source in | `start`, `duration`, `mediaStart` in ticks of 705 600 000 per second |
| Source file | `sourceBin` entry with `src` = original path; source-track `range` in the track's own `editRate` |
| Position and size | `translation0/1` (pixels from canvas centre, y up) and `scale0/1` (relative to source size), as static parameter values |
| Clip gain | AMFile `attributes.gain` (linear) |
| Cross dissolve | `Fade` transition between the two adjacent medias |
| Dip to black | `FadeThroughBlack` when the template has it, else `Fade` (warning) |
| Dip to white | `Fade` (warning) |

Not exported, reported in `edit.report.json`: crop, clip backgrounds, audio crossfades of transitions, gaps (Camtasia positions are absolute), disabled clips.

## UI

Export → **Camtasia project** writes `edit.tscproj` to the project's exports folder. CLI: `videoflow export BUNDLE --camtasia [--camtasia-template PATH]`.

Validation: unit tests cover lanes, linked pairs as UnifiedMedia, exact tick conversion at 25 fps, source ranges, placement and gain values, unique ids, Fade between adjacent medias, cloning of user template structures (custom keys, transition names, keyframes removed), dropping private metadata, fallbacks and the export service. With a real Camtasia 2023.4.3 project as template, every generated structure (UnifiedMedia, VMFile, AMFile, transition, source-bin entry, top level, timeline) has the same keys as the original and no template content leaks. Opening the result in Camtasia remains a manual check on Windows; y orientation of `translation1` is assumed (y up) until confirmed.
