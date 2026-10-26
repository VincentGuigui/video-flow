# Video-Flow: specification set (draft v0.1)

**Video-Flow** is a local-first *assembly tool* for footage shot with many retakes, starting with product unboxing videos.
It ingests a folder of rushes, transcribes and analyses every clip, groups equivalent takes into **beats**, lays the alternatives of each beat side by side (aligned on what is said or shown) so the best one can be picked quickly, then:

- renders the final video with **FFmpeg**, or
- hands the edit over to a full editor through **OpenTimelineIO**, FCPXML, FCP7 XML, EDL or a native **Camtasia** project.

Initial draft: 2026-10-23. Latest accepted architecture revision: 2026-10-25. Read revisions 08–10 before implementing earlier sections; later revisions take precedence where they conflict.

## Documents

| # | File | Content |
|---|------|---------|
| 01 | [01-feasibility.md](01-feasibility.md) | Feasibility study: verdict per requirement, state of the art, standards, risks, effort |
| 02 | [02-functional-spec.md](02-functional-spec.md) | Glossary, workflows, functional requirements (prioritised), UI and wireframes, NFRs |
| 03 | [03-architecture.md](03-architecture.md) | Technical architecture, stack decisions, API, job system, media handling, repo layout |
| 04 | [04-analysis-pipeline.md](04-analysis-pipeline.md) | Transcription, similarity detection, beat clustering, alignment, quality scoring, local LLM tasks |
| 05 | [05-data-model.md](05-data-model.md) | Project bundle, entities, JSON schema, compilation to OTIO, representation of alternates |
| 06 | [06-render-export.md](06-render-export.md) | FFmpeg render pipeline, transition catalog, encoding presets, export formats and mappings |
| 07 | [07-roadmap.md](07-roadmap.md) | Phases, exit criteria, risk register, open questions |
| 08 | [08-review-and-plan.md](08-review-and-plan.md) | Review of choices, verified hypotheses, hardware policy, revised implementation plan (supersedes 01-07 where they conflict) |
| 09 | [09-interactive-editor.md](09-interactive-editor.md) | Wireframe-driven editor, linked/independent media, explicit gaps, trim modes, keyboard, transforms and sidecar analysis (supersedes conflicting earlier rules) |
| 10 | [10-desktop-shell.md](10-desktop-shell.md) | Accepted PySide6/Qt WebEngine desktop shell, native local-path imports without copying, lifecycle, security and platform acceptance gates |

Suggested reading order: 10, 09 and 08 for current decisions, then 02, 04 and 05 for product behavior and data, 03 and 06 for implementation, and 07 for historical roadmap context.

## Key decisions at a glance

| Topic | Decision |
|-------|----------|
| Positioning | Pre-edit / assembly tool (selects + rough cut + simple finishing). **Not** a general-purpose NLE. |
| Project format | `project.json` (take graph, source of truth) compiled to **OpenTimelineIO** (`timeline.otio`), the de facto open interchange standard. |
| Rendering | FFmpeg CLI (7.x minimum, 8.x recommended) driven by generated filter graphs. Sufficient for cuts, trims, `xfade` transitions, B-roll overlay, loudness normalisation. |
| Transcription | Pluggable ASR with word-level timestamps: Whisper large-v3-turbo (faster-whisper / WhisperX / whisper.cpp) or NVIDIA Parakeet TDT 0.6B v3. |
| Grouping | Embeddings + lexical alignment + visual and audio similarity do the grouping. The tiny local LLM only labels beats and flags segments (false starts, off-topic). |
| Stack | Python 3.13 + FastAPI backend; React/Vite interface hosted in a PySide6 + Qt WebEngine desktop window. Native drag-and-drop references original media in place. Browser mode is optional for development/diagnostics. See 08–10. |
| Privacy | 100 % local by default. Optional cloud LLM provider (Anthropic API) behind an explicit setting. |

## Conventions for the implementation phase

- One commit per functional change, short functional commit message, no AI co-author trailer.
- No refactoring, rollback, framework or major version change without explicit approval.
- Keep `README.md` up to date with the essentials; extend `docs/` as the project grows.

Latest accepted revisions: [10 — Desktop shell](10-desktop-shell.md) and [11 — Editor refinements and local AI settings](11-editor-refinements.md). They supersede conflicting earlier decisions.
