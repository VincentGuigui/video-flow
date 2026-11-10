# Timeline and clip flow

The bottom of the window holds the edit: one ruler with the cursor and the range, and below it the clips on numbered lanes. Timeline and clip flow share the same time axis, zoom and scroll, and the cursor and range guides run across both.

## Clips and lanes

- A **video** clip and its **audio** sit together, the audio just below; they are *linked* and move, split and trim together. The chain button between them detaches them ([audio tracks](audio-tracks.md)).
- Lanes stack: the highest lane is on top in the picture. Retakes of the same sentences are stacked on parallel lanes when imported ([retake grouping](../import-analysis/retake-grouping.md)), so you can [compare them](compare-takes.md) and keep one.
- The box on each clip enables or disables it. Only enabled clips play, render and export. Several stacked takes may be enabled at the same time.
- The edit has no unwanted holes: time that no clip covers is closed up. An **empty clip** keeps its time on purpose (black and silence).
- Text clips (titles, lower thirds), image clips and freeze frames sit on video lanes ([clip effects](../finishing/clip-effects.md), [still images](../import-analysis/still-images.md)).
- Hovering a clip shows a one-line description ([clip tooltip](clip-tooltip.md)).

## Moving and zooming

Drag a clip to move it in time or to another lane; green guides show when its edges line up with other clips. **Ctrl + wheel** zooms around the pointer, **Shift + wheel** scrolls, and the buttons at the right of the timeline header zoom and fit the edit.

## Focusing a clip

Double-click a clip (in the flow or on the timeline) to focus it: the timeline shows that clip with up to two seconds before and after, playback and navigation stay within it, and the preview shows its handles. **Back to full edit** (or **Esc**, or a double-click on an empty part of the flow) returns to the whole edit.

## Cutting and removing

The toolbar below the flow shows the number of clips and the clip actions:

- **Split** (S) cuts the selected clip (and its linked audio) at the cursor.
- **Freeze** (F) inserts a still of the frame at the cursor ([still images](../import-analysis/still-images.md#freeze-frame)).
- **Delete** (Delete) removes the selected range, or the selected clip when there is no range, and keeps its time as an empty clip.
- **Ripple** (Backspace) removes it and moves later clips earlier.
- **Trim clip to range**, **Auto-trim silence** ([range and trim](range-and-trim.md)), **Compare takes** ([compare takes](compare-takes.md)), **Title** and **Lower third** ([clip effects](../finishing/clip-effects.md)).

Undo and redo work on whole gestures, linked clips included.

## Trimming

A selected video clip has two pairs of handles at each edge:

- the **top** handles *ripple*: the clip gets longer or shorter and later clips move;
- the **bottom** handles *keep the total time*: the time freed or taken is given to, or taken from, the neighbouring empty time. Extending past that empty time moves later clips.

A clip can only be extended as far as its media goes (still clips have no limit). Neighbouring empty clips merge into one.

An audio clip has one handle per edge. Trimming it keeps the place it occupied: the freed time stays in the edit as silence instead of moving later clips. Disabling or removing the clip gives that time back; Delete keeps it as an empty clip.

## Linking separate clips

A video clip and an audio clip that start at the same time and have the same length can be linked from the Clip tab (**Link audio** / **Link video**); each keeps its own source offset. After that they move, split and trim together. **Detach audio & video** separates them again.

## Technical notes

Clip positions and lengths are integer frames of the project rate. Retained audio time is stored on the clip as `heldRange` and rendered as black and silence when nothing else covers it; `layout()` (backend `editor/models.py`, mirrored in `frontend/src/model.ts`) closes up uncovered time ([data model](../../architecture/data-model.md)). Property fields update the preview while typing; their saves are grouped, and Save, Save as, Export and undo flush pending changes first.
