# Compare takes

When you import several takes of the same sentences, Video-Flow stacks them on parallel lanes ([retake grouping](../import-analysis/retake-grouping.md)). **Compare takes** plays them side by side so you can keep the best one.

## Opening it

Select a clip that has stacked takes (a video clip, or its audio) and click **Compare takes (N)** in the toolbar below the flow; N is the number of takes. The button appears when there are at least two. The takes are the video clips on any lane that overlap the selected clip in time, enabled or not.

## In the comparison

- One card per take: its number, name, duration, a player and the words said inside the part of the take you kept.
- The words that only one take says are highlighted. All takes share a **sync word**, the first word of the reference take that every take says (preferably a word of four letters or more); it is underlined.
- **Play all** (or **Space**) starts every player half a second before its sync word and stops it at the end of its kept part, so you hear the same sentence in each take. Only one take is audible: click the speaker on a card to switch (by default the reference take, the first enabled one).
- **Pick** (or key **1–9**) keeps that take, with its audio, and disables the others and their audio. It is one undo step. Several takes may be enabled before you pick.
- **Esc** closes the comparison. The editor shortcuts are off while it is open.

Picking part of a take, or comparing camera angles recorded at the same time, is not available yet.

## Technical notes

Rules: [editor behaviour](../../architecture/editor-behaviour.md#compare-takes). Tests: [validation record](../../validation/2026-11-12-manual-pages.md#compare-takes). Covers CMP-01 to CMP-04 of the [functional spec](../../product/functional-spec.md); its beats are not used.
