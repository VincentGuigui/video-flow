# Clip effects — 2026-10-28

Features from the backlog in [Camtasia findings](../../decisions/0003-camtasia-findings.md), one section each. They apply to the editor, preview, MP4 render and Camtasia export.

## Effects tab

Clip effects are edited in the **Effects** tab of the properties panel (video, audio and text clips; empty clips have none), below the transitions of a video clip. Each effect in use is a card: its name, a one-line summary (fade length, speed, number of ranges), a fold arrow and a remove button (which resets the effect). **Add effect** lists the effects that apply to the clip and are not in use, with a short description. The list comes from `frontend/src/effects.ts`: each entry says which clips it applies to, whether it is in use, its summary, and how to add (default values) and remove it; its card body is in `frontend/src/ui/EffectBodies.tsx`. A new effect is one entry and one body. Animation has its own tab ([keyframed transforms](keyframes.md)). The Clip tab keeps the clip's own settings (title text, source range, transform, volume, links, trim) and a **Transitions & effects** button that opens the Effects tab.

Validation: `frontend/src/effects.test.ts` covers which effects apply to each kind of clip, adding and removing fades on linked clips, removing speed, mute and duck ranges, and finding the cuts. A browser check clicked a cut marker (Effects tab opened with that cut highlighted), chose Dip to black, added Fade in and Speed from Add effect and removed Fade in.

## Edge fades

- Each clip has `fadeIn` and `fadeOut` (frames, default 0). Effects tab → **Fade in** / **Fade out** cards set them in seconds (added at 0.5 s); linked video and audio get the same values.
- Picture: the clip's opacity ramps from 0 at its start over `fadeIn` frames and to 0 over its last `fadeOut` frames. A clip on the bottom lane therefore fades from/to black; a clip over other lanes fades from/to what lies below. Audio: volume ramps from/to silence over the same frames.
- Fades are capped at the clip length, combine with transitions (the longer fade wins on an edge) and survive splits: the left part keeps the fade-in, the right part the fade-out.
- Render: alpha `fade` on the clip and its backdrop, `afade` on its audio. OTIO: audio fades on audio clips (metadata for other tools). Camtasia: a one-sided `Fade` (only `rightMedia` for a fade-in, only `leftMedia` for a fade-out), skipped where a transition already uses that edge.

Validation: backend tests cover planning, capping and merging with a dissolve; a real render checks black → red → black ramps at five frames; the Camtasia test checks one-sided fades and no duplicate on a transition edge. Frontend tests mirror the planning, opacity at both edges and split behaviour. A browser check set a 1 s fade-in, saw it saved on both linked clips and the preview go from opacity 0 to 1.

## Clip speed

- Each clip has `speed` (0.1–10, default 1): source frames played per timeline frame. Its timeline length is `round(span / speed)` (half up), where `span = sourceOut − sourceIn`. Linked video and audio always share one speed (validated).
- Effects tab → **Speed** card: presets from 25 % to 400 %, and **Fit to range**, which sets the speed so the clip exactly fills the timeline range ([range and trim](../editing/range-and-trim.md)). Changing speed ripples later clips by the change in length; one undo step.
- Every timeline↔source conversion uses the clip's speed: split boundaries, trims (handles drag in timeline frames, sources move at speed), transcript timecodes and ranges, SRT and paper-edit word times, auto-trim, transition handles (available source frames divided by speed), waveform and preview sync (`playbackRate` = speed).
- Render: `setpts=(PTS−STARTPTS)/speed` then resampling to the project rate for picture; `atempo` (chained within 0.5–2) for pitch-preserving audio; output length exact.
- OTIO and EDL: clip speed is metadata only (warning). Camtasia: `mediaDuration` is the source span and `scalar` = duration / mediaDuration as a fraction (e.g. `1/2` at 200 %), with `clipSpeedAttribute`.

Validation: backend tests cover durations and conversions, linked-speed validation, transition handles at speed, the atempo chain, exact renders at 2× (25 frames) and 0.5× (100 frames) with matching audio, and the Camtasia scalar. Frontend tests cover ripple and linked speed, split and trim in source frames at 2×. A browser check set 200 % on a 90 s clip: the edit became 45 s, the preview played at 2×, and the rendered MP4 had 1350 frames and 45 s of audio.

## Zoom & pan

Replaced by [keyframed transforms](keyframes.md): a zoom is a keyframe with a larger size between keyframes at the normal size.

## Mute ranges and ducking

- An audio clip has `volumeRanges`: `{start, end, gainDb, ramp, kind}`. Times are **source frames** (like keyframes), `gainDb` runs from −60 (silence) to 0, `ramp` is the fade length outside the range, `kind` is `mute` or `duck`. Where ranges overlap, the lowest gain wins. Linked video and audio share the ranges of the audio clip.
- Effects tab → **Mute ranges** card → **Mute timeline range** silences the part of the selected clip's audio inside the timeline range (0.1 s ramps); the picture is kept. Each muted range is listed with its timecodes and a remove button.
- Music is any audio clip that is not linked to a video (an imported audio file, or detached audio); its level is the clip gain and its fades the edge fades above. For such a clip, the **Ducking** card (Effects tab) → **Duck under speech** lowers it by 15 dB wherever the other enabled audio clips have transcribed words: words closer than 0.5 s are merged, each range starts 0.2 s before the speech and ends 0.3 s after, with 0.3 s ramps. **Update ducking** recomputes the ranges after edits; removing the card deletes them. Mute ranges are kept by both.
- Preview: each clip's gain is multiplied by its envelope at the current frame. Render: FFmpeg `volume` with a per-frame expression over the clip's timeline seconds, after the speed change. Camtasia: `volume` keyframes on the AMFile (ramp to the range gain from `start − ramp`, back to 1 at `end`). OTIO and EDL: ranges are not exported. SRT subtitles and the paper edit leave out the words said inside a mute range (by the middle of the word).

Validation: backend tests cover the envelope (ramps, overlaps, silence), the FFmpeg expression, a real render whose RMS drops to silence in a muted range and by the duck gain in a ducked range, and the Camtasia keyframes. Frontend tests mirror the envelope, mapping the timeline range to source frames, duck range merging and padding. A browser check muted the first 19 s of a talk clip and ducked a music clip under its speech (3 ranges); the rendered MP4 measured −30 dB music outside speech, −45 dB under speech and the talk muted in its range.

## Titles and lower thirds

- A **text clip** (`kind: "text"`) has no asset and carries a `title`: `{text, style, size, color, box, boxColor, boxOpacity}`. `text` holds lines separated by newlines; `style` is `title` or `lower_third`; `size` is the first line's font size relative to the picture height. Text clips play on video lanes (they stack, move, trim, split, enable and fade like pictures), always at normal speed; their source range has no limit, so they can be extended from either edge. Transitions, keyframes, crop and speed do not apply to them.
- Flow toolbar → **Title** adds a 3 s centred title at the cursor, **Lower third** a 5 s "Name / Role" lower third; both go on the lane above every picture they cover. Clip properties → **Text**: the text (saved when the field loses focus, Ctrl+Enter), style (switching resets size and box to the style's defaults), size (small to extra large), text colour, box behind text with its colour and opacity.
- Layout: every line sits in its own font box (ascender to descender of Inter). A title is centred in the picture, all lines bold at the same size. A lower third is aligned 6 % from the left edge with its last line ending at 90 % of the height; the first line is bold, the others regular at 70 % of its size. With a box, each line gets its own box (padding 0.35 × 0.12 of the first line's size, 0.15 between boxes); without one, the text gets a soft 50 % black shadow.
- Drawing: the backend draws the title with Pillow and the bundled Inter Regular/Bold (SIL OFL 1.1) as a transparent picture of the output size. Render: the picture is an FFmpeg input looped for the clip's frames, faded in alpha and overlaid at its lane, so titles need no `drawtext` (missing from some FFmpeg builds). Preview: the same picture from `GET /api/title?spec=<title JSON>`, drawn at the project size, so the preview matches the render exactly.
- Camtasia: a text `Callout` (`text` shape, or `text-rectangle` filled with the box colour and opacity) placed at the layout's bounds, with font Inter, the lines joined by `\r` and per-line text attributes (size, weight, colour); edge fades become one-sided Fades. Camtasia draws one rectangle around all lines rather than one box per line, and no shadow. OTIO and EDL: text clips are gaps; OTIO keeps the title in the gap's metadata (warning `editor_titles`).

Validation: backend tests cover the model rules, title and lower-third layout, the drawn picture (transparent around the text, shadow, box colour and opacity, exact box bounds), the title endpoint, one picture per distinct title in the graph, a real render with a centred title and a boxed lower third in their windows only, with exact frame count, and the Camtasia callouts (shapes, ranges in UTF-16 units, colours, position below and left of centre, one-sided fade), including a titles-only export. Frontend tests cover adding titles above the picture, shared lanes, editing and renaming, head extension and the speed rule, and fades. A browser check added a title and a lower third at the cursor, edited their text, saw the preview show the backend picture, rendered the MP4 (title and lower third as previewed) and exported to Camtasia.
