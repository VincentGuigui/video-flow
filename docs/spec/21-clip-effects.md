# 21. Clip effects — 2026-10-28

Features from the backlog in [20](20-camtasia-inspired-backlog.md), one section each. They apply to the editor, preview, MP4 render and Camtasia export.

## Edge fades

- Each clip has `fadeIn` and `fadeOut` (frames, default 0). Clip properties → **Fades** sets them in seconds; linked video and audio get the same values.
- Picture: the clip's opacity ramps from 0 at its start over `fadeIn` frames and to 0 over its last `fadeOut` frames. A clip on the bottom lane therefore fades from/to black; a clip over other lanes fades from/to what lies below. Audio: volume ramps from/to silence over the same frames.
- Fades are capped at the clip length, combine with transitions (the longer fade wins on an edge) and survive splits: the left part keeps the fade-in, the right part the fade-out.
- Render: alpha `fade` on the clip and its backdrop, `afade` on its audio. OTIO: audio fades on audio clips (metadata for other tools). Camtasia: a one-sided `Fade` (only `rightMedia` for a fade-in, only `leftMedia` for a fade-out), skipped where a transition already uses that edge.

Validation: backend tests cover planning, capping and merging with a dissolve; a real render checks black → red → black ramps at five frames; the Camtasia test checks one-sided fades and no duplicate on a transition edge. Frontend tests mirror the planning, opacity at both edges and split behaviour. A browser check set a 1 s fade-in, saw it saved on both linked clips and the preview go from opacity 0 to 1.

## Clip speed

- Each clip has `speed` (0.1–10, default 1): source frames played per timeline frame. Its timeline length is `round(span / speed)` (half up), where `span = sourceOut − sourceIn`. Linked video and audio always share one speed (validated).
- Clip properties → **Speed**: presets from 25 % to 400 %, and **Fit to range**, which sets the speed so the clip exactly fills the timeline range (15). Changing speed ripples later clips by the change in length; one undo step.
- Every timeline↔source conversion uses the clip's speed: split boundaries, trims (handles drag in timeline frames, sources move at speed), transcript timecodes and ranges, auto-trim, transition handles (available source frames divided by speed), waveform and preview sync (`playbackRate` = speed).
- Render: `setpts=(PTS−STARTPTS)/speed` then resampling to the project rate for picture; `atempo` (chained within 0.5–2) for pitch-preserving audio; output length exact.
- OTIO and EDL: clip speed is metadata only (warning). Camtasia: `mediaDuration` is the source span and `scalar` = duration / mediaDuration as a fraction (e.g. `1/2` at 200 %), with `clipSpeedAttribute`.

Validation: backend tests cover durations and conversions, linked-speed validation, transition handles at speed, the atempo chain, exact renders at 2× (25 frames) and 0.5× (100 frames) with matching audio, and the Camtasia scalar. Frontend tests cover ripple and linked speed, split and trim in source frames at 2×. A browser check set 200 % on a 90 s clip: the edit became 45 s, the preview played at 2×, and the rendered MP4 had 1350 frames and 45 s of audio.

## Zoom & pan

- A video clip has `zooms`: `{start, end, scale, x, y, easeIn, easeOut}`. Times are **source frames**, so zooms stay on their content through trims, splits and speed changes; `x`/`y` place the focus point in the picture (0..1 from top-left).
- A zoom eases in from 1 to `scale` (smoothstep), holds, and eases back to 1 by `end`; ramps shrink to fit short zooms. Zooms enlarge the picture toward the focus point *inside the clip's frame*, so a full-frame clip never shows borders and a picture-in-picture zooms within its box.
- Clip properties → **Zoom & pan**: **Add zoom over range** creates a 200 % zoom over the part of the clip inside the timeline range, easing in over 0.3 s and out over 1 s (the user's Camtasia habit). Each zoom lists its timecodes, a scale (150–400 %), a focus box (click where to zoom) and a remove button.
- Preview: CSS scale toward the focus point inside a clipping box (the video element is never remounted). Render: FFmpeg `zoompan` with per-frame expressions over the clip's own frames, one focus point per zoom. Camtasia: keyframes on `scale0/1` and `translation0/1` in media time (ramp to the zoomed value over `easeIn` from `start`, back over `easeOut` before `end`); Camtasia scales about the clip centre, so translation compensates to keep the focus point fixed. For a clip smaller than the canvas, Camtasia zooms the whole layer rather than inside its box.
- OTIO and EDL: zooms are metadata only.

Validation: backend tests cover the curve (ease, hold, shortened ramps), expressions only for zooms inside the clip, invalid zooms, a real render that magnifies the left half of a red/blue picture to fill the frame and returns, with exact frame count, and Camtasia keyframes (times, ramps, scale, compensating translation). Frontend tests mirror the curve, mapping with speed and range-based creation. A browser check added a zoom from the range, set its focus by clicking, saw the preview go from 1× to 2× toward that point, and rendered the MP4.

## Mute ranges and ducking

- An audio clip has `volumeRanges`: `{start, end, gainDb, ramp, kind}`. Times are **source frames** (like zooms), `gainDb` runs from −60 (silence) to 0, `ramp` is the fade length outside the range, `kind` is `mute` or `duck`. Where ranges overlap, the lowest gain wins. Linked video and audio share the ranges of the audio clip.
- Clip properties → **Audio** → **Mute range** silences the part of the selected clip's audio inside the timeline range (0.1 s ramps); the picture is kept. Each muted range is listed with its timecodes and a remove button.
- Music is any audio clip that is not linked to a video (an imported audio file, or detached audio); its level is the clip gain and its fades the edge fades above. For such a clip, **Duck under speech** lowers it by 15 dB wherever the other enabled audio clips have transcribed words: words closer than 0.5 s are merged, each range starts 0.2 s before the speech and ends 0.3 s after, with 0.3 s ramps. **Update ducking** recomputes the ranges after edits; **Remove ducking** deletes them. Mute ranges are kept by both.
- Preview: each clip's gain is multiplied by its envelope at the current frame. Render: FFmpeg `volume` with a per-frame expression over the clip's timeline seconds, after the speed change. Camtasia: `volume` keyframes on the AMFile (ramp to the range gain from `start − ramp`, back to 1 at `end`). OTIO and EDL: ranges are clip metadata only.

Validation: backend tests cover the envelope (ramps, overlaps, silence), the FFmpeg expression, a real render whose RMS drops to silence in a muted range and by the duck gain in a ducked range, and the Camtasia keyframes. Frontend tests mirror the envelope, mapping the timeline range to source frames, duck range merging and padding. A browser check muted the first 19 s of a talk clip and ducked a music clip under its speech (3 ranges); the rendered MP4 measured −30 dB music outside speech, −45 dB under speech and the talk muted in its range.
