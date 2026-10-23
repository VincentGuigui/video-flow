# 05. Data model and project format

## 1. Principles

1. **Two layers.** *Analysis* (transcripts, features, relations) is derived, cached and rebuildable. *Decisions* (beats accepted by the user, selections, trims, transitions, order) are authored and precious. They live in different files.
2. **`project.json` is the source of truth for decisions**; `timeline.otio` is a compiled artefact regenerated on every save.
3. **Stable identifiers.** Segment ids are deterministic: `seg_<assetId>_<startMs>_<endMs>_<kind>`. Clip items also store their source range, so a clip keeps working even if re-analysis changes segmentation (the broken link is flagged, not fatal).
4. **Time.** Source times are stored in seconds with microsecond precision (word timestamps and VFR sources do not map cleanly to frames). Quantisation to the project frame grid happens at compile time, so changing the project frame rate never accumulates rounding errors.
5. **Never touch source media**; all paths are absolute with a project-relative fallback for relinking.
6. **Versioned schema** with forward migrations.

## 2. Project bundle

```
Unboxing-X200.videoflow/
├── project.json          # decisions, settings (source of truth, schema-versioned)
├── timeline.otio         # compiled current cut (regenerated on save)
├── history.jsonl         # command log (undo across sessions, audit)
├── analysis.sqlite       # jobs, transcripts, segments, relations, metrics (rebuildable)
├── features/             # embeddings .npy, peaks .bin, per asset
├── cache/
│   ├── proxies/          # <assetId>.mp4
│   ├── thumbs/           # sprites + index
│   └── previews/         # transition preview renders
├── exports/              # .otio, .otioz, .fcpxml, .xml, .edl, .tscproj, .srt, paper edit
└── renders/              # final renders + logs
```

`cache/` and `features/` can be deleted to save space; they are regenerated. Deleting `analysis.sqlite` forces a full re-analysis but keeps all decisions.

## 3. Entities

TypeScript notation for readability; the canonical definition is the Pydantic model (exported as JSON Schema).

```ts
type Seconds = number;          // source time, microsecond precision
type Id = string;

interface Project {
  schemaVersion: 1;
  id: Id;
  name: string;
  revision: number;             // incremented on every saved change
  settings: ProjectSettings;
  assets: Asset[];
  beats: Beat[];                // ordered: array order = story order
  overlays: OverlayItem[];      // V2 (B-roll), A2 (music)
  transitions: Transition[];    // on main-line cuts
  constraints: GroupingConstraint[];
  markers: Marker[];
}

interface ProjectSettings {
  width: number; height: number;          // e.g. 1920 x 1080
  frameRate: { num: number; den: number }; // e.g. 30/1, 30000/1001
  sampleRate: 48000;
  language: string;                        // "fr"
  loudnessTarget: { integrated: number; truePeak: number }; // -14, -1
  clipPadding: { before: Seconds; after: Seconds };          // 0.15, 0.30
  defaultTransition: { type: TransitionType; duration: Seconds };
  grouping: { sensitivity: number; weights?: Record<string, number> };
  llmProvider: "none" | "local" | "anthropic";
}

interface Asset {
  id: Id;                       // short hash of content hash
  path: string;                 // absolute
  relPath?: string;             // relative to project parent, for relink
  contentHash: string;          // xxh3 of size + first/last 4 MB + middle samples
  probe: {
    duration: Seconds; width: number; height: number; rotation: 0 | 90 | 180 | 270;
    fps: number; vfr: boolean; hdr: "none" | "hlg" | "pq";
    hasAudio: boolean; creationTime?: string; creationTimeReliable: boolean;
  };
  syncGroupId?: Id;             // simultaneous recordings
  syncOffset?: Seconds;         // offset to the sync group's reference clock
}

interface Beat {
  id: Id;
  label: string;
  summary?: string;
  role: "intro" | "content" | "transition" | "outro" | "off_topic";
  kind: "speech" | "visual";
  included: boolean;            // excluded beats stay in the project but not in the cut
  locked: boolean;              // user-edited: re-clustering keeps it as is
  takes: TakeRef[];
  cut: ClipItem[];              // what this beat contributes to the main line (usually 1 item)
}

interface TakeRef {
  segmentId: Id;
  assetId: Id;
  range: { start: Seconds; end: Seconds };   // segment bounds at time of grouping
  status: "selected" | "alternate" | "rejected";
  score?: number;
  flags: Array<"false_start" | "off_topic" | "fillers" | "clipped_audio" | "last_take">;
  alignOffset?: Seconds;        // display offset relative to the selected take
}

interface ClipItem {
  id: Id;
  assetId: Id;
  segmentId?: Id;               // provenance, optional
  sourceIn: Seconds;
  sourceOut: Seconds;
  enabled: boolean;
  audio: {
    mode: "linked" | "replaced" | "muted";
    replacement?: { assetId: Id; sourceIn: Seconds };   // TL-07: audio from another take
    gainDb: number;
    fadeIn: Seconds; fadeOut: Seconds;
  };
  syncAngle?: Id;               // for sync groups: which camera asset is shown
}

interface Transition {
  id: Id;
  leftItemId: Id;               // cut between these two main-line items
  rightItemId: Id;
  type: TransitionType;         // see 06-render-export.md §4
  duration: Seconds;
  alignment: "center" | "start" | "end";   // relative to the cut
  audio: "follow" | "cut" | { type: "crossfade"; duration: Seconds };
  params?: Record<string, unknown>;
}

interface OverlayItem {
  id: Id;
  track: "V2" | "A2";
  assetId: Id;
  sourceIn: Seconds; sourceOut: Seconds;
  anchor: { itemId: Id; offset: Seconds };   // connected to a main-line item (moves with ripple edits)
  audio: { mode: "muted" | "mix"; gainDb: number };
  fit?: "fill" | "fit" | { x: number; y: number; scale: number };
}

interface GroupingConstraint {
  type: "must_link" | "cannot_link";
  a: Id; b: Id;                 // segment ids
  createdAt: string;
}

interface Marker { id: Id; target: { itemId?: Id; assetId?: Id }; time: Seconds; note: string; color?: string }
```

### Derived main line
The main line (V1 + A1) is not stored separately: it is the concatenation of `beat.cut` for every beat with `included = true`, in array order. Promoting a take replaces the beat's `cut` with a fresh item built from the new segment (padding applied, trims reset); transitions attached to the old item's edges are re-attached to the new item.

## 4. Example `project.json` (abridged)

```json
{
  "schemaVersion": 1,
  "id": "prj_7f3a",
  "name": "Unboxing X200",
  "revision": 42,
  "settings": {
    "width": 1920, "height": 1080, "frameRate": {"num": 30, "den": 1},
    "sampleRate": 48000, "language": "fr",
    "loudnessTarget": {"integrated": -14, "truePeak": -1},
    "clipPadding": {"before": 0.15, "after": 0.30},
    "defaultTransition": {"type": "dissolve", "duration": 0.5},
    "grouping": {"sensitivity": 0.5},
    "llmProvider": "local"
  },
  "assets": [
    {"id": "a01", "path": "/Users/v/Rushes/IMG_0412.MOV", "contentHash": "xxh3:9c1e...",
     "probe": {"duration": 48.2, "width": 3840, "height": 2160, "rotation": 0, "fps": 29.97,
               "vfr": true, "hdr": "hlg", "hasAudio": true,
               "creationTime": "2026-10-20T14:02:11+02:00", "creationTimeReliable": true}}
  ],
  "beats": [
    {
      "id": "b03", "label": "Accessoires dans la boîte", "role": "content", "kind": "speech",
      "included": true, "locked": false,
      "takes": [
        {"segmentId": "seg_a04_12200_26400_sp", "assetId": "a04", "range": {"start": 12.2, "end": 26.4},
         "status": "selected", "score": 0.82, "flags": ["last_take"]},
        {"segmentId": "seg_a02_3100_19900_sp", "assetId": "a02", "range": {"start": 3.1, "end": 19.9},
         "status": "alternate", "score": 0.61, "flags": ["fillers"], "alignOffset": -0.4},
        {"segmentId": "seg_a02_0300_4400_sp", "assetId": "a02", "range": {"start": 0.3, "end": 4.4},
         "status": "rejected", "score": 0.2, "flags": ["false_start"]}
      ],
      "cut": [
        {"id": "c07", "assetId": "a04", "segmentId": "seg_a04_12200_26400_sp",
         "sourceIn": 12.05, "sourceOut": 26.7, "enabled": true,
         "audio": {"mode": "linked", "gainDb": 0, "fadeIn": 0, "fadeOut": 0}}
      ]
    }
  ],
  "overlays": [
    {"id": "o02", "track": "V2", "assetId": "a09", "sourceIn": 2.0, "sourceOut": 6.5,
     "anchor": {"itemId": "c07", "offset": 3.0}, "audio": {"mode": "muted", "gainDb": 0}, "fit": "fill"}
  ],
  "transitions": [
    {"id": "t01", "leftItemId": "c06", "rightItemId": "c07", "type": "dissolve",
     "duration": 0.5, "alignment": "center", "audio": "follow"}
  ],
  "constraints": [
    {"type": "cannot_link", "a": "seg_a02_3100_19900_sp", "b": "seg_a07_0000_9800_sp", "createdAt": "2026-10-23T10:12:00Z"}
  ],
  "markers": []
}
```

## 5. Analysis store (`analysis.sqlite`)

| Table | Key columns |
|-------|-------------|
| `jobs` | id, kind, scope, stage, status, progress, params_hash, error, started_at, ended_at |
| `stage_outputs` | cache_key, asset_id, stage, version, path, created_at |
| `words` | asset_id, idx, text, norm, start, end, prob, is_filler |
| `segments` | id, asset_id, kind, start, end, text, shot_ids, embedding_row |
| `relations` | seg_a, seg_b, type, score, details_json |
| `metrics` | segment_id, name, value |
| `beat_proposals` | run_id, beat_key, segment_ids_json, label, summary, role, best_take, reason |

Embeddings live in `features/<assetId>.text.npy` / `.visual.npy` with row indexes referenced from SQLite.

## 6. Compilation to OpenTimelineIO

Deterministic function `compile(project) -> otio.schema.Timeline`:

| Project element | OTIO element |
|-----------------|--------------|
| Project | `Timeline` (name, `global_start_time` configurable, default 00:00:00:00, option 01:00:00:00 for broadcast-style NLE defaults) |
| Tracks | `Stack` with `Track` V1 "Main", V2 "B-roll" (video); A1 "Main audio", A2 "Music" (audio) |
| ClipItem on V1 | `Clip` with `ExternalReference` (target_url, available_range from probe) and `source_range` quantised to project rate |
| Linked audio | Matching `Clip` on A1 with same range; link id in metadata (OTIO has no link concept) |
| Replaced audio | A1 `Clip` referencing the other asset, range shifted by the alignment offset |
| Transition | `Transition` between the two clips; `transition_type` = `SMPTE_Dissolve` for dissolve, `Custom_Transition` otherwise; `in_offset` / `out_offset` from duration and alignment (center: T/2 each) |
| Overlay | `Clip` on V2/A2 at its resolved timeline position, `Gap` elsewhere |
| Disabled clip | `Clip.enabled = false` |
| Marker | `Marker` on the clip or timeline |
| Proxy | Optional second media reference: `media_references = {"DEFAULT_MEDIA": original, "proxy": proxy}`, active key `DEFAULT_MEDIA` |

Metadata namespace `videoflow` (ignored by other tools, preserved by most):

```json
{"videoflow": {"projectId": "prj_7f3a", "revision": 42, "itemId": "c07", "beatId": "b03",
              "segmentId": "seg_a04_12200_26400_sp", "takeStatus": "selected",
              "transition": {"type": "wipeleft", "alignment": "center"}}}
```

Notes:
- OTIO transitions use **handles** (media beyond the visible in/out). The render follows the same semantics (see 06 §3) so the exported timeline and the FFmpeg output have the same duration and the same frames.
- `target_url` style (plain absolute path vs `file://` URL) is a per-export option; interop tests decide the default per target (Resolve has been reported to reject `file://` URLs in OTIO files written by Premiere).
- Requires OpenTimelineIO ≥ 0.17 and `OpenTimelineIO-Plugins` for non-native adapters.

## 7. Representing alternates outside Video-Flow

OTIO has no "alternate take" concept. Export option *include alternates* (EXP-07):

| Target | Representation |
|--------|----------------|
| OTIO / FCP7 XML | Extra video tracks "ALT 1" … "ALT n", `enabled = false`, each alternate placed at its beat's start on the main line plus its alignment offset; `Gap` elsewhere. Audio of alternates on disabled audio tracks or omitted (option). |
| FCPXML | Native `<audition>` element per beat: selected take as the active clip, alternates as inactive ones (custom post-processing of the adapter output). |
| Camtasia | Extra tracks, disabled/hidden, same placement rule as OTIO. |
| EDL | Not supported (single track); alternates listed as comments optional. |

## 8. Schema evolution

- `schemaVersion` integer; migrations `vN -> vN+1` are pure functions, chained at load time.
- Before migrating, the original file is copied to `project.v<N>.bak.json`.
- Unknown fields are preserved on load/save (forward compatibility for minor additions).
