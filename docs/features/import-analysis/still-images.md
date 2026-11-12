# Still images and freeze frames

## Importing a picture

PNG, JPEG, WebP, BMP and TIFF pictures are imported like video and audio: **Import media**, or drop them on the window ([importing media](importing.md)). They are referenced where they are, never copied or modified. In Project media a picture shows **Image** instead of a duration. Pictures are never analysed (there is nothing to transcribe), even when analysis is on.

## Image clips

An imported picture is added at the end of the flow as a **3 second image clip**. It behaves like a video clip without sound:

- **Any length.** Drag either edge to make it as long or as short as you want; a picture has no end. Both kinds of trim handle work, and it snaps like any clip ([timeline and clip flow](../editing/unified-timeline.md#trimming)).
- Split it, move it, stack it on lanes, enable or disable it like a clip.
- **Transitions** always work with it: a dissolve has all the picture it needs ([transitions](../finishing/transitions.md)).
- Fades, [keyframes](../finishing/keyframes.md), position, size, crop and backgrounds work as on video. **Speed** does not apply.
- Its properties say **Image clip**, with its duration and no source range, Transcript tab or audio link.

## Freeze frame

A freeze frame turns the picture under the cursor into a still that lasts as long as you like.

1. Select a video clip (or its audio) and put the cursor on the frame to freeze.
2. Click **Freeze** in the toolbar below the flow, or press **F**.

A **3 second still** of that frame is inserted at the cursor, and everything after it moves later by 3 seconds, on every lane. The still is selected, ready to be made longer or shorter. Where the freeze goes depends on the cursor:

- **Inside the clip**: the clip and its audio are cut at the cursor, the freeze goes between the two parts, and the second part continues from the frozen frame. The audio is silent under the freeze.
- **On the first frame**: the freeze goes before the clip, and takes its incoming transition.
- **On the last frame**: the freeze goes after the clip, holding its last frame, and takes its outgoing transition.

The freeze is named after its clip with "· freeze", keeps the picture's position, size and background as shown at that frame, and its properties say **Freeze frame**. It is an image clip like any other. A still can't itself be frozen.

## In other editors

The MP4 shows pictures and freezes exactly as the preview. **Camtasia** receives image clips ([Camtasia export](../output/camtasia-export.md)); **OTIO** receives freeze frames as freeze effects; the **EDL** writes them as freeze-frame events. SRT and paper edit have nothing for them.

## Technical notes

Data, preview, render and export mapping: [transitions, effects, titles, keyframes and still clips](../../architecture/effects-and-titles.md#still-clips-and-freeze-frames). Tests: [validation record](../../validation/2026-11-12-manual-pages.md#still-images-and-freeze-frames).
