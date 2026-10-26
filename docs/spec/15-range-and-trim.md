# 15. Timeline range, transcript trimming and auto-trim — 2026-10-26

This revision supplements 09, 12 and 14.

## Range selector

- The assembly timeline shows a range with a start and an end marker on its ruler, drawn like the cursor.
- By default the range covers the current timeline range: the focused clip plus 2 s before and after (clamped to the edit), or the whole edit when no clip is focused. Changing focus resets it to that default.
- Dragging a marker moves it (at least one frame between start and end) and selects it. The selected marker is highlighted. Scrubbing the timeline or pressing Escape deselects it; Escape with no marker selected leaves clip focus as before.
- **Space** (and the play button) plays the range once. With a marker selected it plays from 2 s before to 2 s after that marker instead. Playback starts at the cursor when the cursor is inside that window, otherwise at the window start. At the end, playback stops and the cursor returns to the window start. Space while playing stops.

## Transcript-driven trimming

- In the Transcript tab, clicking a topic sets the range to that topic; collapsing it resets the range to its default. Clicking a word sets the range to that word; Shift+click extends it from the last clicked word. Times outside the clip's trimmed range are ignored. The user can then adjust the markers on the timeline.
- **Trim clip to range** (Clip tab) keeps only the part of the selected clip inside the range. Its linked audio is trimmed with it, and later clips on every lane move earlier by the removed time (ripple). It is disabled when the range does not shorten the clip. One undo step; the range then returns to its default.

## Auto-trim silence

- **Auto-trim silence** (Clip tab) trims the selected clip to its first and last spoken words, keeping the project clip padding (default 0.15 s before, 0.30 s after), with ripple and linked audio as above. It only shortens, never extends. It needs a transcript and is disabled when there is no speech or nothing to remove. It applies to the selected clip only.

Validation: frontend tests cover the default range, the window around a marker, playback start, marker ordering, trim to range with linked audio and ripple, auto-trim padding and no-speech. A browser check on a served project confirmed marker drag and selection, playback around a marker with return to the window start, word selection, trim, undo and auto-trim.
