# Keyframed transforms

A keyframe records how a video clip looks at one moment: its **position, size, rotation, crop and opacity**. With two or more keyframes, Video-Flow animates the clip smoothly from one to the next. Use it for a slow push-in, a picture sliding in, a fade, a turn. Image clips and freeze frames can be animated too ([still images](../import-analysis/still-images.md)).

## Animating a clip

1. Select a video clip and open the **Animation** tab of the properties panel.
2. Put the cursor where the animation starts and click **Add at cursor** (or press **K**): a keyframe holds the clip as it looks there.
3. Move the cursor to where it should end and add another keyframe.
4. With the cursor on that keyframe, change the values (or drag and resize the picture in the preview): **X**, **Y**, **Scale** (uniform, around the centre), **Width**, **Height**, **Rotation**, **Opacity** and the four **Crop** values. Between the two keyframes, every value changes gradually.

Before the first keyframe and after the last, the clip holds that look. Once a clip has keyframes, changing a value at a spot with no keyframe adds one there, so you can simply move the cursor and adjust.

A zoom is simply a keyframe with a larger size between keyframes at the normal size. (Zoom & pan of earlier versions is replaced by this; zooms in older projects are ignored.)

## The keyframe list

Under **KEYFRAMES**, each keyframe shows its time (click to go there), its **easing** and a **×** to remove it. The arrows go to the previous and next keyframe.

- **Smooth** (default) eases in and out of the change that starts at that keyframe; **Linear** changes at a constant speed.
- **Remove animation** deletes every keyframe; the clip keeps the look it has at the cursor.

## On the timeline

The keyframes of the selected clip appear as **diamonds** on the timeline (and on the clip in the flow), within the part of the clip you kept:

- click a diamond to move the cursor there and select it;
- **drag** it to move it in time (never onto another keyframe);
- press **Delete** to remove the selected one.

Without keyframes, the Clip tab's X, Y, Width and Height fields set the clip's look; once animated, the Clip tab sends you to the Animation tab.

## Good to know

- Changing the project's output resolution scales all keyframes with the picture.
- The preview handles show the unrotated box; set the rotation in the Animation tab.
- A very large picture zoomed far in may look slightly softer than the source in the render.

## In other editors

The MP4 shows the animation exactly. **Camtasia** receives keyframes on position, size, rotation and opacity ([Camtasia export](../output/camtasia-export.md)), with Camtasia's own easing; crop is not exported. **OTIO** keeps them as notes for other tools; the **EDL** has none.

## Technical notes

Data, interpolation, render and export mapping: [transitions, effects, titles, keyframes and still clips](../../architecture/effects-and-titles.md#keyframed-transforms). Tests: [validation record](../../validation/2026-11-12-manual-pages.md#keyframes).
