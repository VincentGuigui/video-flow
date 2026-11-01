# Video-Flow documentation

Start with the [project README](../README.md) for what Video-Flow does and how to install and run it. The [roadmap](roadmap.md) lists what is built and what comes next; the [release notes](release_notes.md) list major changes per version.

| Folder | Content |
|--------|---------|
| [product/](product/) | What the product must do: [functional specification](product/functional-spec.md) (glossary, workflows, requirements with their status) |
| [features/](features/) | One document per built feature: behaviour, data, render and export mapping, validation. They describe the current behaviour |
| [architecture/](architecture/) | How it is built: [overview](architecture/overview.md), [desktop shell](architecture/desktop-shell.md), [data model](architecture/data-model.md), [analysis pipeline](architecture/analysis-pipeline.md), [render and export](architecture/render-export.md) |
| [decisions/](decisions/) | Dated decision records, numbered in order. Kept as history |
| [reference/](reference/) | [Dependencies](reference/dependencies.md) (versions, licences, accelerators), [desktop runtime](reference/desktop-runtime.md), [workspace layout](reference/workspace-layout.md) |
| [validation/](validation/) | Dated validation records on real hardware |

## Features

| Document | Content |
|----------|---------|
| [Interactive editor](features/interactive-editor.md) | Wireframe-driven editor, linked and independent media, empty clips, trim modes, keyboard, transforms, analysis sidecars |
| [Editor refinements](features/editor-refinements.md) | Project home, save / save as, backgrounds, MP4 export, local AI model settings |
| [Unified timeline](features/unified-timeline.md) | One timeline axis, linking separate clips, audio trimming with retained time, live properties |
| [Audio tracks](features/audio-tracks.md) | Audio of video clips: enable box, detach, restore original audio |
| [Transcript panel](features/transcript-panel.md) | Import summary and titled topic sections, cursor seek, timeline highlight |
| [Range and trim](features/range-and-trim.md) | Timeline range and range playback, trim to range, delete range, auto-trim silence |
| [Compare takes](features/compare-takes.md) | Stacked retakes side by side, synced on a common word, pick with 1–9 |
| [Transitions](features/transitions.md) | Cross dissolve and dips between adjacent clips |
| [Retake grouping](features/retake-grouping.md) | Stacking retakes on import: MiniLM sentence similarity and word overlap |
| [Camtasia export](features/camtasia-export.md) | Template-driven `.tscproj` writer, mapping, limits |
| [Clip effects](features/clip-effects.md) | Edge fades, speed, zoom & pan, mute ranges and ducking, titles and lower thirds |
| [Projects](features/projects.md) | Projects as `<name>.video-flow` folders in the working folder, relative media, recent list, home page |
| [Workspace zones](features/workspace-zones.md) | Zone focus, Ctrl+A and Delete per zone, media removal, thumbnails, cache folder |

## Decisions

| Record | Content |
|--------|---------|
| [0000 Initial roadmap](decisions/0000-initial-roadmap.md) | First phase plan, risk register, open questions |
| [0001 Feasibility](decisions/0001-feasibility.md) | Feasibility study and state of the art |
| [0002 Review and plan](decisions/0002-review-and-plan.md) | Stack review, verified hypotheses, NPU → GPU → CPU policy, implementation plan |
| [0003 Camtasia findings](decisions/0003-camtasia-findings.md) | What the user's Camtasia projects use, and the feature backlog drawn from them |

## Writing rules

- A new feature gets a document in `features/` (or a section in the closest one) and a row above; `README.md`, the [roadmap](roadmap.md) and, for a major change, the [release notes](release_notes.md) are updated in the same change.
- A replaced or removed behaviour is amended everywhere in `docs/`, so no document describes something that no longer exists. Decision records are history and are not rewritten.
- Architecture documents describe the system as built; keep them in step with the code when a change affects them.
