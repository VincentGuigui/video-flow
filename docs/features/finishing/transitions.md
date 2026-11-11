# Transitions

A transition blends two video clips that touch on the same lane, at the cut between them. Video-Flow offers four choices:

| Choice | What you see |
|--------|--------------|
| **Cut** | No transition: the picture changes at once (the default) |
| **Dissolve** | The next picture fades in over the previous one |
| **Dip black** | The picture fades to black, then the next one fades in from black |
| **Dip white** | The same through white |

The sound of linked clips follows the picture: a crossfade for a dissolve, a fade out then in for a dip. A transition never changes the length of the edit.

## Adding a transition

1. In the clip flow, each cut between two video clips on one lane has a round marker: **+** for a plain cut, a filled marker once it has a transition. Click it. (A transition band on the timeline opens the same thing.)
2. The properties panel opens on the **Effects** tab, on the card of that cut. Pick **Cut**, **Dissolve**, **Dip black** or **Dip white**.
3. For a transition, set its **Duration** in seconds. New transitions last 0.5 s.

A selected video clip shows one card for the cut before it (*In · from …*) and one for the cut after it (*Out · to …*). **Apply … to all cuts** gives every cut of the edit the chosen type and duration.

The timeline marks each transition over the frames it covers, and the preview shows it.

## Good to know

- **A dissolve needs a little extra footage.** It uses the media just beyond the cut. When a clip has less than needed, the transition is shortened and the card says by how much. When there is none at all, the last frame of the first clip is held while the next picture fades in, so the edit keeps its length. Dips need no extra footage.
- A still image or a freeze frame can always dissolve ([still images](../import-analysis/still-images.md)).
- If you move a clip so the two no longer touch, the transition is kept but ignored until they touch again. Splitting the first clip keeps the transition on the cut after the second part.
- The render shows exactly what the preview shows.

## In other editors

The **Camtasia** export carries dissolves and dips as Camtasia fades ([Camtasia export](../output/camtasia-export.md)). **OTIO** and **EDL** carry the transitions of the lowest video lane; the EDL writes them all as dissolves. Transitions on upper lanes are rendered in the MP4 but not exported, and audio crossfades are not written. The export reports what it left out.

## Technical notes

Model, handles, shortening rules and the render and export mapping are in [transitions, effects and titles](../../architecture/effects-and-titles.md#transitions); tests are listed in the [validation record](../../validation/2026-11-11-finishing-features.md). This page covers TR-01, TR-02, TR-04, TR-06 (shortening) and TR-07 of the [functional spec](../../product/functional-spec.md).
