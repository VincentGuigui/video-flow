# Timeline range, transcript trimming and auto-trim

The **range** marks a part of the edit to play, trim or remove. It shows as two markers on the ruler, drawn like the cursor, and as a tinted band across the timeline and the flow.

## Setting the range

- **By default** it covers the focused clip plus two seconds before and after, or the whole edit when no clip is focused. Focusing another clip resets it.
- **Drag a marker** to move it. The marker you drag is selected and highlighted; scrubbing the timeline or pressing **Esc** deselects it (Esc again leaves clip focus).
- **From the transcript** ([transcript panel](../import-analysis/transcript-panel.md)): click a topic to set the range to it (click again to reset); click a word to set the range to that word, **Shift + click** another word to extend it, or select text in the transcript lines. Times outside the kept part of the clip are ignored. You can then fine-tune the markers.

## Playing the range

**Space** (or the play button) plays the range once; Space again stops it. With a marker selected it plays from two seconds before to two seconds after that marker instead — handy to check a cut. Playback starts at the cursor when it is inside that window, otherwise at its start, and the cursor goes back to the start when it ends.

## Trimming and removing

The actions are in the toolbar below the flow ([timeline and clip flow](unified-timeline.md)):

- **Trim clip to range** keeps only the part of the selected clip inside the range. Its audio is trimmed with it, and later clips on every lane move earlier by the removed time. Disabled when the range doesn't shorten the clip. The range then returns to its default.
- **Delete** and **Ripple** (Delete / Backspace) remove the range inside the selected clip and its audio, or the whole clip when there is no range. Delete keeps the time as an empty clip; Ripple closes the gap.
- **Auto-trim silence** trims the selected clip to its first and last spoken words, keeping 0.15 s before and 0.30 s after. It only shortens, needs a transcript, and is disabled when there is no speech or nothing to remove. It applies to the selected clip only.

Each action is one undo step.

## Technical notes

Rules: [editor behaviour](../../architecture/editor-behaviour.md#range-and-trim). Tests: [validation record](../../validation/2026-11-12-manual-pages.md#range-and-trim).
