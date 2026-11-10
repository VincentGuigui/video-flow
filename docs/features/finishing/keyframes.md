# Keyframed transforms

A video clip (image and freeze clips included) can animate its transform: position, size, rotation, crop and opacity. Keyframes replace the former zoom & pan effect: a zoom is two or more keyframes with a larger size.

## Data

- `Transform` (`editor/models.py`, `frontend/src/model.ts`) has `x`, `y`, `width`, `height` (output pixels), the four crop fractions, `rotation` (degrees, clockwise, about the centre of the box; default 0) and `opacity` (0–1; default 1).
- `EditorClip.keyframes`: `{frame, transform, ease}`. `frame` is a **source frame**, so keyframes stay on their content through trims, splits and speed changes (a still clip's head trim moves them with the clip). Keyframes are kept sorted, at distinct frames, on video clips only.
- Between two keyframes every value is interpolated; `ease` shapes the change that starts at the keyframe: `smooth` (smoothstep, default) or `linear`. Before the first keyframe and after the last, the transform holds. Without keyframes, `transform` applies to the whole clip; with keyframes, it is not used.
- One definition of the interpolation: `editor/keyframes.py` (render, exports), mirrored in `frontend/src/keyframes.ts` (preview, editing).

## Editing

- **Animation tab** of the properties panel (video clips): **Add at cursor** (or **K**) adds a keyframe holding the transform shown at the cursor; arrows go to the previous or next keyframe. Each keyframe of the clip's visible range is listed with its time (click to go there), its easing and a remove button. Below, the values at the cursor: X, Y, Scale (uniform, about the centre, relative to the clip's transform), Width, Height, Rotation, Opacity and the four crops. Without keyframes they change the clip's transform; with keyframes, changing one sets the keyframe at the cursor, or adds one there (auto-key). **Remove animation** deletes every keyframe; the clip keeps the transform shown at the cursor.
- **Preview handles** follow the same rule: dragging or resizing the selected clip edits its transform, or the keyframe at the cursor once it has keyframes. The handles show the unrotated box.
- **Timeline:** the keyframes of the selected clip are diamonds on the assembly timeline (within the clip's visible range). Click one to move the cursor there and select it; drag it to move it inside the clip (never onto another keyframe); **Delete** removes the selected keyframe. The flow card shows the same diamonds.
- The Clip tab's transform fields apply to clips without keyframes; an animated clip shows the number of keyframes and a button to the Animation tab.
- Changing the output resolution maps every keyframe like the transform. A freeze frame takes the transform shown at the frozen frame, without keyframes.

## Preview, render and exports

- **Preview:** the clip box takes the interpolated position and size, crops with `clip-path`, turns with a CSS rotation about its centre and multiplies the picture's opacity.
- **Render:** a clip with keyframes, a rotation or an opacity below 1 takes the per-frame path in `render/graph.py`: an animated crop is a first `perspective` (crop region stretched to the frame; a constant crop is a plain `crop`), then the picture inside a 2 px transparent border goes onto a full-frame canvas, and a second `perspective` maps it to the four corners of its box, rotated about the centre. Their corner expressions are piecewise functions of the source frame, read from the filter's frame counter. Opacity uses `colorchannelmixer`, driven per frame by `sendcmd` when it changes. A box larger than 1.25× the output is drawn on a canvas twice the output size, then scaled down. Other clips keep the plain `scale`/`crop`/`overlay` path.
- **Camtasia:** keyframes become keyframes on `translation0/1`, `scale0/1`, `rotation2` (radians, counter-clockwise) and `opacity`, in media time; each ramps from the previous keyframe to its value. Camtasia's own easing applies (the per-keyframe ease is not carried); crop is not exported. A static rotation or opacity is exported as a parameter value.
- **OTIO:** keyframes are clip metadata (`videoflow.keyframes`), with the warning `editor_keyframes`. EDL does not carry them.

## Projects from earlier versions

The zoom & pan effect is removed without migration (decision of 2026-11-01, [0004 Keyframes replace zoom](../../decisions/0004-keyframes-replace-zoom.md)): a project saved with zooms opens, its zooms are ignored.

## Validation

- `backend/tests/render/test_keyframes_render.py`: interpolation (hold, linear, smooth, sorting) and the piecewise expression; renders of an opacity fade over a lower clip, an animated crop revealing the clip below, and a 45° rotation (centre, corners and tips of the box).
- `backend/tests/render/test_transitions_render.py::test_keyframes_magnify_toward_the_left_edge_and_return`: a 400 % push-in on the left edge and back, with exact frames.
- `backend/tests/exporters/test_camtasia.py::test_keyframes_become_camtasia_keyframes_in_media_time`.
- `frontend/src/keyframes.test.ts`: interpolation, auto-key, add, move within the visible range, remove (the last one becomes the transform), clear, visible keyframes and still-clip head trims.
- A browser check added two keyframes on an image clip (the second at 50 %, 30°, 60 % opacity), saw the preview halfway between them and the diamonds on the timeline and the flow card.
