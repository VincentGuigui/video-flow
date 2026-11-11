# Properties panel

The properties panel (tabs Clip, Effects, Transcript and Project; see [clip effects](../finishing/clip-effects.md) and [transitions](../finishing/transitions.md)) sits on the right of the editor area. Its layout is a per-viewer preference, remembered in the browser storage of the window (`videoflow.panel`); without storage it starts from the defaults every time. Code: `frontend/src/panel.ts` (layout, bounds, storage), `frontend/src/ui/PropertiesDock.tsx` (frame, controls, resize, folding).

## Width

Dragging the left edge of the panel resizes it, from 200 px up to 640 px and never more than half of the editor area. Default: 280 px.

## Height

The first button at the right of the tabs switches between two heights:

- **Half** (default): the panel stands beside the preview only. The timeline and the clip flow keep the full width; the preview gets narrower.
- **Tall**: the panel takes the full height of the editor area. The preview, the timeline and the clip flow all get narrower.

## Pinned and unpinned

The second button pins or unpins the panel.

- **Pinned** (default): the panel takes its width from the editor area, as described above.
- **Unpinned**: the panel floats over the other blocks, whose width does not change. When the pointer leaves it, it folds after 0.3 s into a narrow **Properties** strip along the right edge; the pointer on the strip (or a click, or keyboard focus) opens it again. It does not fold while its edge is being dragged, while a mouse button is held, or while one of its drop-down lists is open.

The panel is hidden on windows narrower than 850 px, as before.

## Validation

`frontend/src/panel.test.ts` covers the width bounds and reading a stored layout (defaults, invalid data). A browser check resized the panel, switched to tall, unpinned it, saw it fold into the strip when the pointer left and open again on the strip, switched back to half while unpinned, and found the layout stored.
