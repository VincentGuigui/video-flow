# Data model and project format

A project is a `*.videoflow` folder. Its `project.json` holds a schema-versioned `Project` (`backend/videoflow/project/models.py`) whose `editor` field carries the interactive edit, the `EditorDocument` (`backend/videoflow/editor/models.py`, mirrored in `frontend/src/model.ts`). Exporters and the renderer read the edit through one resolved, frame-quantised timeline. See [overview](overview.md) for the components, [analysis pipeline](analysis-pipeline.md) for derived data and [render and export](render-export.md) for the consumers.

## Conventions

| Topic | Rule |
|-------|------|
| JSON keys | camelCase on disk and on the wire (`CamelModel.dump()`: `model_dump(by_alias=True)`); Python attributes are snake_case. |
| Unknown data | Every model keeps unknown fields (`extra="allow"`); enum-like fields are open and keep unknown values verbatim (`UnknownValue`). A newer file survives a load/save cycle in an older app. |
| Project ids | Opaque `<prefix>_<ULID>` strings (`core/ids.py`: `prj`, `ast`, `beat`, `clip`, `tr`, ...), never reused or parsed. Editor clips use `clp_…`, link ids `lnk_…`. |
| Source time | Integer microseconds (`…Us` fields, `Micros`) in `Project` assets, legacy entities, analysis words and topics. Never float seconds. |
| Edit time | Integer project-rate frames in the `EditorDocument`. |
| Rates | `Rational` `{ "num": 30000, "den": 1001 }`, never a float. |
| Quantisation | `frames(us) = round_half_up(us * fps)`; a range `[in, out)` covers `frames(out) - frames(in)` frames; `frame_to_us` is its inverse (`core/time.py`). Timecode is displayed non-drop. |

## Project bundle

`project/store.py` (`Bundle`) defines the layout; `Bundle.create` makes the folders marked *created*.

| Path | Content |
|------|---------|
| `project.json` | The `Project`, written atomically (same-folder temp file, fsync, rename; retried on Windows sharing errors). |
| `project.v<N>.bak.json` | Original file kept before a schema migration rewrites it. |
| `history.jsonl` | Append-only log of committed command batches (write-ahead and audit). |
| `analysis/` *(created)* | `analysis/sidecars/<sha256>.json`: bundle copy of every analysis sidecar. |
| `features/` *(created)* | `features/sentences/<hash>.npy`: sentence vectors for [retake grouping](../features/retake-grouping.md). |
| `cache/proxies/` *(created)* | Playback proxies keyed by asset content hash. |
| `cache/thumbs/` *(created)* | Thumbnails. |
| `cache/peaks/` | Waveform peaks (`.bin`). |
| `cache/titles/` | Title pictures drawn by Pillow for the render. |
| `cache/render/<id>/` | Render scratch files. |
| `cache/previews/` *(created)* | Reserved; nothing writes it. |
| `exports/` *(created)* | `edit.otio`, `edit.otioz`, `edit.edl`, `edit.tscproj`, `edit.srt`, `edit.md`/`edit.csv`, `edit.report.json`. |
| `renders/` *(created)* | `render-<id>.mp4`. |

`Bundle.timeline_file` names `timeline.otio`, but no code writes it: OTIO is produced only on export. Everything under `analysis/`, `features/` and `cache/` is rebuildable. Source media stay where they are and are never copied or modified.

## Project

```json
{
  "schemaVersion": 1,
  "app": { "writer": "videoflow 0.x", "minReader": 1 },
  "id": "prj_01JB6Z4Q2X8M7T3V9KD0R5WFHN",
  "name": "Unboxing X200",
  "revision": 42,
  "pipelineVersion": null,
  "settings": { "width": 1920, "height": 1080, "frameRate": { "num": 30, "den": 1 }, "sampleRate": 48000, "language": "fr", "...": "..." },
  "assets": [ { "id": "ast_…", "path": "D:/Rushes/A001.mp4", "relPath": "../Rushes/A001.mp4", "contentHash": "…", "probe": { "…": "…" }, "previewPath": "…" } ],
  "syncGroups": [], "beats": [], "overlays": [], "transitions": [], "constraints": [], "markers": [],
  "overrides": { "transcriptEdits": [], "dismissedSegmentIds": [] },
  "editor": { "version": 1, "clips": [], "transitions": [] }
}
```

| Field | Meaning |
|-------|---------|
| `revision` | Incremented once per committed command batch; used for optimistic locking. |
| `settings` | `width`, `height` (output canvas), `frameRate`, `sampleRate`, `language`, plus `loudnessTarget`, `clipPadding`, `defaultTransition`, `grouping`, `llmProvider`. |
| `assets[]` | One per imported source: absolute `path`, `relPath` relative to the bundle's parent (relink), `contentHash` (full hash up to 64 MB, sampled fingerprint beyond; cache key and duplicate detection), `probe`. Import adds `previewPath` as an extra field. |
| `probe` | `durationUs`, `video` (`width`, `height`, `rotation`, `frameRate`, `vfr`, `hdr`, `codec`) or `null`, `audioStreams[]` (`index`, `channels`, `sampleRate`, `codec`, `language`), `creationTime`, `creationTimeReliable`. |
| `editor` | The `EditorDocument`, stored as an extra field (absent until the first interactive edit). |
| `syncGroups`, `beats`, `overlays`, `transitions`, `constraints`, `markers`, `overrides`, `pipelineVersion` | Legacy beats/cut model, see below. |

`invariant_violations()` checks unique ids per kind, resolvable asset/beat references and well-formed source ranges.

## Editor document

All positions and lengths are integer project-rate frames. `start` is the timeline position; `sourceIn`/`sourceOut` are source frames.

```json
{
  "version": 1,
  "clips": [
    { "id": "clp_…", "kind": "video", "assetId": "ast_…", "name": "A001.mp4",
      "start": 0, "sourceIn": 12, "sourceOut": 312, "layer": 0, "enabled": true,
      "linkId": "lnk_…", "gainDb": 0, "speed": 1.0, "fadeIn": 0, "fadeOut": 15,
      "transform": { "x": 0, "y": 0, "width": 1920, "height": 1080,
                     "cropLeft": 0, "cropRight": 0, "cropTop": 0, "cropBottom": 0 },
      "resizeReference": null, "background": { "mode": "transparent", "color": "#000000" },
      "heldRange": null, "zooms": [], "volumeRanges": [], "title": null },
    { "id": "clp_…", "kind": "text", "assetId": null, "name": "Title", "start": 0,
      "sourceIn": 0, "sourceOut": 90, "layer": 1, "linkId": null,
      "title": { "text": "Chapter 1", "style": "title", "size": 0.08, "color": "#ffffff",
                 "box": false, "boxColor": "#000000", "boxOpacity": 0.75 } }
  ],
  "transitions": [ { "id": "…", "leftId": "clp_…", "rightId": "clp_…", "type": "dissolve", "duration": 15 } ]
}
```

| Element | Fields and rules |
|---------|------------------|
| `kind` | `video` and `audio` need `assetId`; `gap` (authored empty time: black/silence) and `text` have no asset and no link. Only text clips have `title`; text clips play at speed 1 and sit on video lanes. |
| `layer` | Lane number 0–999; higher video layers composite on top. Video and audio lanes are numbered independently. |
| `speed` | 0.1–10, source frames per timeline frame. Timeline `duration = round_half_up(span / speed)` with `span = sourceOut - sourceIn` ≥ 1. |
| `transform` | Picture rectangle in output pixels plus crop fractions (`crop*` in `[0, 1)`, opposite crops sum below 1). `resizeReference` keeps the canvas size and transform a resize started from. `background`: `transparent`, `color` or `blur`. Frontend-only `fitMode` survives as an extra field. |
| `heldRange` | `{start, end}` timeline frames kept by a standard audio trim without a placeholder clip. |
| `fadeIn`, `fadeOut` | Edge fades in frames (picture from what lies below, audio from silence). |
| `gainDb` | −60 to +24 dB. |
| `zooms[]` | `start`, `end` (source frames), `scale` (>1, ≤8), focus `x`, `y` (0–1), `easeIn` (9), `easeOut` (30). |
| `volumeRanges[]` | `start`, `end` (source frames), `gainDb` (−60 = silence, ≤0), `ramp` (4 frames, outside the range), `kind` `mute` or `duck`. |
| `linkId` | Joins exactly one video and one audio clip, which must share `start`, `duration` and `speed`. |
| `transitions[]` | `type` `dissolve`, `dip_black` or `dip_white`; `duration` 1–3600 requested frames, centred on the cut between `leftId` and `rightId`. Dormant (ignored, never deleted) while the clips are missing or not adjacent on one lane. |

Clip ids are unique. On commit (`SetEditor`), `validate_assets` also checks that each media clip's asset exists, has the needed stream and that `sourceOut` fits the source duration. `layout()` (mirrored in the frontend) packs the assembly: enabled clips (and held ranges) are merged into covered intervals and uncovered time is removed, so only explicit `gap` clips keep empty time. Feature rules live in [interactive editor](../features/interactive-editor.md), [range and trim](../features/range-and-trim.md), [clip effects](../features/clip-effects.md), [transitions](../features/transitions.md) and [audio tracks](../features/audio-tracks.md).

## Commands, undo and history

Edits are commands (`project/commands.py`): pure functions returning the edited copy and an exact inverse. The client sends `PATCH /api/project` with `{baseRevision, commands[]}`; `Bundle.commit` rejects a stale revision (HTTP 409), applies the batch all-or-nothing, appends a `history.jsonl` line (`schemaVersion`, `revision`, `baseRevision`, `at`, `commands`, `inverses`, fsynced) and then saves `project.json`. The response returns the project, the editable document and the inverses; the frontend keeps them as its undo stack (last 100 steps) and undoes by sending them as a new batch. On load, history lines newer than the saved revision are replayed (crash between log and save).

The full command set (33 types plus `Batch`) covers project, settings, assets, sync groups, beats, takes, cut items, transitions, overlays, constraints, markers, transcript edits and `SetEditor`. The interactive API (`check_commands` in `api/app.py`) accepts only:

| Command | Use |
|---------|-----|
| `SetEditor` | Replace the whole `EditorDocument` (one gesture = one undo step); `null` removes it. |
| `SetSettings`, `RenameProject` | Output format, name. |
| `AddAsset`, `RelinkAsset` | Only for assets and paths that come from a native file selection or a server-side import. |
| `RemoveAsset` | Only when nothing in the legacy model references the asset. |
| `Batch` | Of the above. |

The other commands remain in the schema and are exercised only by backend tests; no UI or API path issues them. Server-side imports commit `AddAsset` + `SetEditor` directly through `Bundle.commit`.

## Versioning and migrations

`SCHEMA_VERSION` is 1. `project/migrations.py` chains pure `vN → vN+1` functions over the raw camelCase dict (`MIGRATIONS` is empty today). Additive changes need no bump, since unknown fields and enum values are preserved. `app.minReader` is the lowest schema version allowed to write the file: when it exceeds the app's version, the project opens read-only. A newer `schemaVersion` is loaded as is, never downgraded. The `EditorDocument` carries its own `version` (1).

`project/schema.py` exports JSON Schemas of `Project` and of the command list; goldens `backend/tests/fixtures/project_v1.schema.json` and `commands_v1.schema.json` fail a test when models change without `uv run python -m videoflow.project.schema --write`. The editor document appears in the commands golden (through `SetEditor`), not in the project golden, because it is an extra field.

## Legacy beats/cut model

The original model is still in the schema, the commands and the legacy resolver. The current UI neither displays nor edits it.

| Entity | Content |
|--------|---------|
| `beats[]` | Story-ordered `label`, `summary`, `role`, `kind`, `included`, `locked`, `takes[]` (`segmentId`, `assetId`, `range`, `status` selected/alternate/rejected, `needsRelink`) and `cut[]` clip items (`sourceInUs`, `sourceOutUs`, `enabled`, `audio` mode/replacement/gain/fades, `angleAssetId`). The main line is the concatenation of enabled cut items of included beats. |
| `transitions[]` | On the cut after `afterItemId` (23 open types, `durationUs`, `alignment`, `audio`, `params`); dormant when not adjacent. |
| `overlays[]`, `syncGroups[]`, `constraints[]`, `markers[]`, `overrides` | V2/A2 overlays anchored to a beat or project time; multicam sync offsets; must/cannot-link grouping constraints; markers; transcript corrections and dismissed segments. |

`editable_document(project)` bridges the two: it returns the stored `editor` field, or, when absent, converts the legacy resolved timeline into an `EditorDocument` (video and audio clips per resolved clip, linked when the legacy audio was linked, V1/A1 on layer 0 and other tracks on layer 1, fit transform per asset). Legacy transitions, fades and overlay fits are not converted. The API, import, Camtasia export and render all start from this document; the render refuses a legacy-only project that has transitions or fades.

## Resolved timeline

`timeline/resolved.py` is the contract shared by the OTIO compiler, EDL, SRT and paper edit. `timeline.resolve.resolve(project)` uses `resolve_editor` when an `editor` document exists, otherwise the legacy beats resolver.

| Type | Content |
|------|---------|
| `ResolvedTimeline` | `projectId`, `revision`, `rate`, `width`, `height`, `sampleRate`, `duration` (frames), `tracks`, `transitions`, `dormantTransitions`, `beats`, `markers`, `warnings` (`code`, `message`). |
| `ResolvedTrack` | `id` (`V1`…`Vn`, `A1`…`An`, one per used layer, bottom up), `kind`, `clips`. |
| `ResolvedClip` | `itemId`, `track`, `assetId` (`__gap__` for gap and text clips), `timelineStart`, `duration`, `sourceInFrame`, `sourceInUs`/`sourceOutUs`, handles and `availableBefore`/`availableAfter`, `audio` (`mode`, `gainDb`, fade frames). From the editor it also carries `kind` (`media`/`gap`), `layer`, `transform`, and `speed` and `title` when set. |
| `ResolvedTransition` | `afterItemId`, `beforeItemId`, `type`, `state`, `duration`, `cutFrame`, `leftFrames`, `rightFrames`, `audioDuration`. Editor transitions above the bottom video lane are rendered but not resolved (warning). |

Zooms, volume ranges, held ranges, backgrounds and video fades are not in the resolved timeline: the FFmpeg render and the Camtasia exporter read the `EditorDocument` directly, and warnings (`editor_speed`, `editor_titles`, `editor_transforms`, `editor_transition_audio`) list what other formats lose.

## OTIO compilation

`exporters/otio_compile.py` builds a fresh OTIO `Timeline` from the resolved timeline: one OTIO track per resolved track (split into extra lanes on overlap), gaps for uncovered time and for gap/text clips, `ExternalReference` with portable `file://` URLs, transitions on V1/A1 only (SMPTE dissolve, others custom). Each clip's `metadata.videoflow` is its resolved clip dump, so gain, fades, transforms, speed and titles travel as metadata only. Optional disabled `ALT` tracks list unused legacy takes. Details are in [render and export](render-export.md).

## Analysis sidecar

Analysis lives outside `project.json`. `editor/analysis.py` writes `<source stem>.json` beside the source (also reads `<source name>.json`), atomically and never over an existing file, and always first caches a copy at `analysis/sidecars/<sha256(contentHash)>.json`, used when the source folder is read-only.

```json
{
  "version": 1,
  "sourceHash": "<asset contentHash>",
  "words": [ { "text": "Bonjour", "startUs": 1200000, "endUs": 1480000, "prob": null } ],
  "summary": "…", "keywords": ["…"], "language": "fr",
  "summaryEngine": "deterministic", "summaryScope": "full transcript",
  "topics": [ { "startUs": 0, "endUs": 61000000, "title": "…", "sentences": [] } ],
  "topicsEngine": "deterministic"
}
```

A sidecar is used only when `version` is 1 and `sourceHash` matches (or is absent); missing topics are derived on read. See [transcript panel](../features/transcript-panel.md) and [retake grouping](../features/retake-grouping.md).
