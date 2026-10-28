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
