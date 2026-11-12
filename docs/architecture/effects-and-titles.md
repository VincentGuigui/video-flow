# Transitions, effects, titles, keyframes and still clips: model and mapping

How the finishing features of the [user manual](../features/README.md) are modelled and mapped to the preview, the render and the exports. User-facing behaviour is in [transitions](../features/finishing/transitions.md), [clip effects](../features/finishing/clip-effects.md), [keyframed transforms](../features/finishing/keyframes.md), [still images](../features/import-analysis/still-images.md) and [Camtasia export](../features/output/camtasia-export.md); [render and export](render-export.md) covers the render graph and the other formats.

## Transitions

- The editor document has `transitions`: `{id, leftId, rightId, type, duration}`, with `type` one of `dissolve`, `dip_black`, `dip_white` and `duration` in project frames (requested, centred on the cut). Cut = no transition.
- A transition is **active** when both clips exist, are enabled video clips on the same lane, and the left clip ends exactly where the right clip starts in the assembly. Otherwise it is dormant: kept, ignored by preview, render and export, and never an edit error. Splitting the left clip keeps the transition on the cut after the right part.
- Total duration is unchanged by any transition.

| Type | Picture | Audio (linked audio follows, TR-04) | Handles |
|------|---------|--------------------------------------|---------|
| Cross dissolve | The left clip continues `after` frames past the cut and the right clip starts `before` frames early (`before` = ⌊T/2⌋, `after` = T − `before`), fading in over the left. | Crossfade over the overlap. | Uses source media beyond the cut. |
| Dip to black / white | The whole picture fades to the colour over `before` frames and back over `after` frames. | Left audio fades out over `before`, right fades in over `after`. | None. |

When the source has too few frames beyond the cut, or a clip is shorter than its half, the transition is **shortened** (TR-06) and a warning is shown in the transition card and in the render log. When no usable overlap remains (zero or one frame), the outgoing last frame is held while the incoming picture fades in after the cut. A still clip has unlimited handles ([still images](../features/import-analysis/still-images.md)). Padded frames receive normalized timestamps in FFmpeg.

- Preview: dissolves are approximated with opacity, dips with a colour layer, audio fades with volume (PRV-02).
- Render: the table above exactly (alpha fade of the incoming clip and its backdrop, colour overlay for dips, `afade` on linked audio). Overlay windows in the render graph use timestamps rather than frame counters, so every clip of a lane renders after a cut.
- OTIO and EDL receive transitions on the V1 lane (dissolve as `SMPTE_Dissolve` / `D`, dips as custom with Video-Flow metadata; EDL writes them as dissolves). Transitions on higher lanes are rendered but not exported, and audio crossfades are not written; both are reported as warnings.

## Effects tab

`frontend/src/effects.ts` lists the effects: each entry says which clips it applies to, whether it is in use, its summary, and how to add (default values) and remove it; its card body is in `frontend/src/ui/EffectBodies.tsx`. A new effect is one entry and one body.

## Edge fades

- Each clip has `fadeIn` and `fadeOut` (frames, default 0); linked video and audio get the same values.
- Picture: the clip's opacity ramps from 0 at its start over `fadeIn` frames and to 0 over its last `fadeOut` frames; audio volume ramps from/to silence over the same frames.
- Fades are capped at the clip length, combine with transitions (the longer fade wins on an edge) and survive splits: the left part keeps the fade-in, the right part the fade-out.
- Render: alpha `fade` on the clip and its backdrop, `afade` on its audio. OTIO: audio fades on audio clips (metadata for other tools). Camtasia: a one-sided `Fade` (only `rightMedia` for a fade-in, only `leftMedia` for a fade-out), skipped where a transition already uses that edge.

## Clip speed

- Each clip has `speed` (0.1–10, default 1): source frames played per timeline frame. Its timeline length is `round(span / speed)` (half up), where `span = sourceOut − sourceIn`. Linked video and audio always share one speed (validated).
- Every timeline↔source conversion uses the clip's speed: split boundaries, trims (handles drag in timeline frames, sources move at speed), transcript timecodes and ranges, SRT and paper-edit word times, auto-trim, transition handles (available source frames divided by speed), waveform and preview sync (`playbackRate` = speed).
- Render: `setpts=(PTS−STARTPTS)/speed` then resampling to the project rate for picture; `atempo` (chained within 0.5–2) for pitch-preserving audio; output length exact.
- OTIO and EDL: clip speed is metadata only (warning). Camtasia: `mediaDuration` is the source span and `scalar` = duration / mediaDuration as a fraction (e.g. `1/2` at 200 %), with `clipSpeedAttribute`.

## Mute ranges and ducking

- An audio clip has `volumeRanges`: `{start, end, gainDb, ramp, kind}`. Times are **source frames** (like keyframes), `gainDb` runs from −60 (silence) to 0, `ramp` is the fade length outside the range, `kind` is `mute` or `duck`. Where ranges overlap, the lowest gain wins. Linked video and audio share the ranges of the audio clip.
- Ducking applies to music, any audio clip not linked to a video: it lowers the clip by 15 dB wherever the other enabled audio clips have transcribed words. Words closer than 0.5 s are merged, each range starts 0.2 s before the speech and ends 0.3 s after, with 0.3 s ramps. Mute ranges are kept by both actions.
- Preview: each clip's gain is multiplied by its envelope at the current frame. Render: FFmpeg `volume` with a per-frame expression over the clip's timeline seconds, after the speed change. Camtasia: `volume` keyframes on the AMFile (ramp to the range gain from `start − ramp`, back to 1 at `end`). OTIO and EDL: ranges are not exported. SRT subtitles and the paper edit leave out the words said inside a mute range (by the middle of the word).

## Titles and lower thirds

- A **text clip** (`kind: "text"`) has no asset and carries a `title`: `{text, style, size, color, box, boxColor, boxOpacity}`. `text` holds lines separated by newlines; `style` is `title` or `lower_third`; `size` is the first line's font size relative to the picture height. Text clips play on video lanes (they stack, move, trim, split, enable and fade like pictures), always at normal speed; their source range has no limit, so they can be extended from either edge. Transitions, keyframes, crop and speed do not apply to them.
- Layout: every line sits in its own font box (ascender to descender of Inter). A title is centred in the picture, all lines bold at the same size. A lower third is aligned 6 % from the left edge with its last line ending at 90 % of the height; the first line is bold, the others regular at 70 % of its size. With a box, each line gets its own box (padding 0.35 × 0.12 of the first line's size, 0.15 between boxes); without one, the text gets a soft 50 % black shadow.
- Drawing: the backend draws the title with Pillow and the bundled Inter Regular/Bold (SIL OFL 1.1) as a transparent picture of the output size. Render: the picture is an FFmpeg input looped for the clip's frames, faded in alpha and overlaid at its lane, so titles need no `drawtext` (missing from some FFmpeg builds). Preview: the same picture from `GET /api/title?spec=<title JSON>`, drawn at the project size, so the preview matches the render exactly.
- Camtasia: a text `Callout` (`text` shape, or `text-rectangle` filled with the box colour and opacity) placed at the layout's bounds, with font Inter, the lines joined by `\r` and per-line text attributes (size, weight, colour); edge fades become one-sided Fades. Camtasia draws one rectangle around all lines rather than one box per line, and no shadow. OTIO and EDL: text clips are gaps; OTIO keeps the title in the gap's metadata (warning `editor_titles`).

## Camtasia writer

`.tscproj` is undocumented JSON. The writer (`exporters/camtasia.py`) clones structures from a template and fills them from the edit.

- Template: `templates/camtasia.tscproj` in the application folder if present (any project saved by the user's Camtasia), or `--camtasia-template PATH` on the CLI; otherwise the built-in default, which reproduces the structures of a real Camtasia 2023.4.3 project (UnifiedMedia, VMFile, AMFile, Fade transition, source-bin entries, track attributes, caption attributes) with neutral values.
- Cloned from the template: top-level settings and version, UnifiedMedia, VMFile, AMFile, transition objects by name, the first track and track-attribute objects, and a video source-bin entry with its source tracks. A missing structure falls back to the built-in one with a warning.
- Never copied from the template: its media, source bin, tracks and private project metadata (autosave path, thumbnail); only `CanvasZoom`, `Fit`, `Language` and `ProfileName` are kept.

| Edit | Camtasia |
|------|----------|
| Video lane (bottom-up) | One track per lane, in lane order; independent audio lanes follow |
| Linked video + audio | `UnifiedMedia` with inner `VMFile` and `AMFile` |
| Unlinked video / audio | `VMFile` / `AMFile` |
| Clip start, duration, source in | `start`, `duration`, `mediaStart` in ticks of 705 600 000 per second |
| Source file | `sourceBin` entry with `src` = original path; source-track `range` in the track's own `editRate` |
| Position and size | `translation0/1` (pixels from canvas centre, y up) and `scale0/1` (relative to source size), as static parameter values |
| Rotation, opacity, keyframes | `rotation2` (radians, counter-clockwise) and `opacity` values; keyframes on these and on position and size, in media time ([keyframed transforms](../features/finishing/keyframes.md)). Rotation is unverified in Camtasia. |
| Still images and freeze frames | `IMFile` (one picture) ([still images](../features/import-analysis/still-images.md)) |
| Clip gain | AMFile `attributes.gain` (linear) |
| Cross dissolve | `Fade` transition between the two adjacent medias |
| Dip to black | `FadeThroughBlack` when the template has it, else `Fade` (warning) |
| Dip to white | `Fade` (warning) |

Not exported, reported in `edit.report.json`: crop, clip backgrounds, audio crossfades of transitions, gaps (Camtasia positions are absolute), disabled clips. CLI: `videoflow export BUNDLE --camtasia [--camtasia-template PATH]`.

## Keyframed transforms

- `Transform` (`editor/models.py`, `frontend/src/model.ts`) has `x`, `y`, `width`, `height` (output pixels), the four crop fractions, `rotation` (degrees, clockwise, about the centre of the box; default 0) and `opacity` (0–1; default 1).
- `EditorClip.keyframes`: `{frame, transform, ease}`. `frame` is a **source frame**, so keyframes stay on their content through trims, splits and speed changes (a still clip's head trim moves them with the clip). Keyframes are kept sorted, at distinct frames, on video clips only.
- Between two keyframes every value is interpolated; `ease` shapes the change that starts at the keyframe: `smooth` (smoothstep, default) or `linear`. Before the first keyframe and after the last, the transform holds. Without keyframes, `transform` applies to the whole clip; with keyframes, it is not used.
- One definition of the interpolation: `editor/keyframes.py` (render, exports), mirrored in `frontend/src/keyframes.ts` (preview, editing).
- Editing: with keyframes, changing a value or dragging in the preview sets the keyframe at the cursor, or adds one there (auto-key). Changing the output resolution maps every keyframe like the transform. A freeze frame takes the transform shown at the frozen frame, without keyframes. The preview handles show the unrotated box.
- **Preview:** the clip box takes the interpolated position and size, crops with `clip-path`, turns with a CSS rotation about its centre and multiplies the picture's opacity.
- **Render:** a clip with keyframes, a rotation or an opacity below 1 takes the per-frame path in `render/graph.py`: an animated crop is a first `perspective` (crop region stretched to the frame; a constant crop is a plain `crop`), then the picture inside a 2 px transparent border goes onto a full-frame canvas, and a second `perspective` maps it to the four corners of its box, rotated about the centre. Their corner expressions are piecewise functions of the source frame, read from the filter's frame counter. Opacity uses `colorchannelmixer`, driven per frame by `sendcmd` when it changes. A box larger than 1.25× the output is drawn on a canvas twice the output size, then scaled down. Other clips keep the plain `scale`/`crop`/`overlay` path.
- **Camtasia:** keyframes become keyframes on `translation0/1`, `scale0/1`, `rotation2` (radians, counter-clockwise) and `opacity`, in media time; each ramps from the previous keyframe to its value. Camtasia's own easing applies (the per-keyframe ease is not carried); crop is not exported. A static rotation or opacity is exported as a parameter value.
- **OTIO:** keyframes are clip metadata (`videoflow.keyframes`), with the warning `editor_keyframes`. EDL does not carry them.
- The zoom & pan effect is removed without migration (decision of 2026-11-01, [0004 Keyframes replace zoom](../decisions/0004-keyframes-replace-zoom.md)): a project saved with zooms opens, its zooms are ignored.

## Still clips and freeze frames

- **Media library:** an image becomes an asset whose probe has `still: true`, no duration and no audio stream (`media/ingest.py`, `IMAGE_EXTENSIONS`). Import does not analyse an image. Instead of a video proxy, a PNG preview is made once in the cache (`media/proxy.py`, `build_still_preview`): at most 1920 px on its longest side, transparency kept. The preview and the thumbnails use it, so formats browsers cannot show (TIFF) and very large photos work too.
- **Clips:** an image clip is a video clip with `stillFrame: 0`. `stillFrame` (`EditorClip.still_frame`) is the source frame a still clip shows for its whole length; `null` means a moving clip. Only video clips at speed 1 can be still. A still clip has no source limit; its source range only measures its length and always starts at 0 (like text clips); splitting it gives two still clips of the same picture. A dissolve onto or from a still clip always has the handles it needs. An image asset accepts only still clips; validation refuses a moving clip on it (`editor/resolve.py`).
- **Freeze:** `freezeFrame` in `frontend/src/model.ts` inserts a 3 s still clip (`stillFrame` = the frozen source frame) named after the clip with “· freeze”, with the transform shown at that frame and the clip's background, no link, fades or keyframes. Every clip from the cursor on moves later by 3 s, on every lane. Inside the clip, the clip and its linked audio are split; on the first frame the freeze goes before the clip and takes over its incoming transition; on the last frame it goes after it and takes over its outgoing transition. Still clips themselves cannot be frozen.
- **Preview:** the clip box shows the PNG preview as a picture (`ui/Preview.tsx`, `Picture`); a still clip of a video shows its video paused on the held frame.
- **Render:** the graph takes the held frame (for an image, its only frame; for a video, frame `stillFrame` after resampling to the project rate), loops it for the clip's frames and places it like any video clip (`render/graph.py`).
- **Camtasia:** a still clip is an `IMFile` (one picture, `mediaDuration` 1), as Camtasia writes images and frozen frames. For an image, the source-bin entry has a single picture track (type 1, range [0, 1]); for a freeze frame, `mediaStart` is the frozen frame in the video's entry. A template without an image clip falls back on the built-in structure, with a warning.
- **OTIO:** an image clip references the image without an available range; a freeze frame references its video at the frozen frame with a `FreezeFrame` effect. Both carry `stillFrame` in the clip metadata.
- **EDL:** a still clip is an event on one source frame with `M2 … 000.0` and `* * FREEZE FRAME`, which editors (and OTIO's reader) take as a freeze frame. SRT and paper edit have no words for it.
