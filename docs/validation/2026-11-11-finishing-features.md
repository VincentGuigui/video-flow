# Validation: transitions, clip effects and Camtasia export

Automated tests and browser checks behind the pages [transitions](../features/finishing/transitions.md), [clip effects](../features/finishing/clip-effects.md) and [Camtasia export](../features/output/camtasia-export.md), moved here from those pages. Behaviour is described in [transitions, effects and titles](../architecture/effects-and-titles.md).

## Transitions

Backend tests cover the plan (handles, shortening, dips, dormant cases) and real renders of each type with exact frame counts and pixel checks at the cut, plus a regression test for sequential clips on one lane. Frontend tests mirror the plan, cover setting, replacing, removing and applying to all cuts, splits, dip opacity and audio gain. A browser check added a dissolve after Delete range, changed its duration, checked the timeline marker, and rendered an MP4 whose frame count matched the timeline.

## Effects tab

`frontend/src/effects.test.ts` covers which effects apply to each kind of clip, adding and removing fades on linked clips, removing speed, mute and duck ranges, and finding the cuts. A browser check clicked a cut marker (Effects tab opened with that cut highlighted), chose Dip to black, added Fade in and Speed from Add effect and removed Fade in.

## Edge fades

Backend tests cover planning, capping and merging with a dissolve; a real render checks black → red → black ramps at five frames; the Camtasia test checks one-sided fades and no duplicate on a transition edge. Frontend tests mirror the planning, opacity at both edges and split behaviour. A browser check set a 1 s fade-in, saw it saved on both linked clips and the preview go from opacity 0 to 1.

## Clip speed

Backend tests cover durations and conversions, linked-speed validation, transition handles at speed, the atempo chain, exact renders at 2× (25 frames) and 0.5× (100 frames) with matching audio, and the Camtasia scalar. Frontend tests cover ripple and linked speed, split and trim in source frames at 2×. A browser check set 200 % on a 90 s clip: the edit became 45 s, the preview played at 2×, and the rendered MP4 had 1350 frames and 45 s of audio.

## Mute ranges and ducking

Backend tests cover the envelope (ramps, overlaps, silence), the FFmpeg expression, a real render whose RMS drops to silence in a muted range and by the duck gain in a ducked range, and the Camtasia keyframes. Frontend tests mirror the envelope, mapping the timeline range to source frames, duck range merging and padding. A browser check muted the first 19 s of a talk clip and ducked a music clip under its speech (3 ranges); the rendered MP4 measured −30 dB music outside speech, −45 dB under speech and the talk muted in its range.

## Titles and lower thirds

Backend tests cover the model rules, title and lower-third layout, the drawn picture (transparent around the text, shadow, box colour and opacity, exact box bounds), the title endpoint, one picture per distinct title in the graph, a real render with a centred title and a boxed lower third in their windows only, with exact frame count, and the Camtasia callouts (shapes, ranges in UTF-16 units, colours, position below and left of centre, one-sided fade), including a titles-only export. Frontend tests cover adding titles above the picture, shared lanes, editing and renaming, head extension and the speed rule, and fades. A browser check added a title and a lower third at the cursor, edited their text, saw the preview show the backend picture, rendered the MP4 (title and lower third as previewed) and exported to Camtasia.

## Camtasia export

Unit tests cover lanes, linked pairs as UnifiedMedia, exact tick conversion at 25 fps, source ranges, placement and gain values, unique ids, Fade between adjacent medias, cloning of user template structures (custom keys, transition names, keyframes removed), dropping private metadata, fallbacks and the export service. With a real Camtasia 2023.4.3 project as template, every generated structure (UnifiedMedia, VMFile, AMFile, transition, source-bin entry, top level, timeline) has the same keys as the original and no template content leaks. Opening the result in Camtasia remains a manual check on Windows; the y orientation of `translation1` is assumed (y up) until confirmed.
