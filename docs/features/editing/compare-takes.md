# Compare takes

Retakes of the same sentences are stacked on parallel lanes when imported ([retake grouping](../import-analysis/retake-grouping.md)). Compare takes plays them side by side so you can keep the best one. (This covers CMP-01 to CMP-04 of the [functional spec](../../product/functional-spec.md); its beats are not used.)

## Takes

- The takes of a selected clip are the video clips on any lane that overlap its assembly time, enabled or not, ordered by lane. A selected audio clip stands for its linked video.
- The toolbar below the clip flow shows **Compare takes (N)** when there are at least two takes.

## Compare view

- A dialog shows one card per take: number, name, duration, a player (proxy media) and the words spoken inside the take's trimmed range.
- **Sync word**: the first word of the reference take (the first enabled take, else the first) that every take says, preferring words of four or more letters. Words said in one take only are highlighted; the sync word is underlined.
- **Play all** (Space) starts every player 0.5 s before its sync word (or at its trimmed start when there is none) and stops each at its trimmed end. Only one take is audible; the speaker button on a card selects it (default: the reference take).
- **Pick** (or keys 1–9) enables the picked take with its linked audio and disables the other takes with theirs; the pick is one undo step. Several takes may be enabled before a pick; all show as picked.
- Escape closes the dialog. Editor shortcuts are inactive while it is open.

Not covered: picking a range inside a take (CMP-05) and multicam angles (CMP-06).

Validation: frontend tests cover take detection (disabled takes, audio selection, overlap), pick enable/disable with linked audio, sync word choice (long-word preference, accents, none) and divergent words. A browser check imported two analysed takes, opened the view from clip properties, verified synced playback with one audible take, divergent highlights, pick with key 2 and Escape.
