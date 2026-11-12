# Properties panel

The panel on the right of the editor shows the settings of the selected clip or of the project, in tabs: **Clip**, **Animation**, **Effects**, **Transcript** and **Project** (see [clip effects](../finishing/clip-effects.md), [keyframed transforms](../finishing/keyframes.md), [transitions](../finishing/transitions.md) and [transcript panel](../import-analysis/transcript-panel.md)). Its layout is remembered between sessions.

## Width

Drag the left edge of the panel to resize it, between 200 and 640 pixels (and at most half of the editor area). It is 280 pixels by default.

## Height

The first button at the right of the tabs switches between two heights:

- **Half** (default): the panel stands beside the preview only. The timeline and the clip flow keep the full width.
- **Tall**: the panel takes the full height of the editor. The preview, timeline and clip flow all get narrower.

## Pinned or floating

The second button pins or unpins the panel.

- **Pinned** (default): the panel takes its place in the layout.
- **Unpinned**: the panel floats over the editor without narrowing it. When the pointer leaves it, it folds after a moment into a narrow **Properties** strip on the right edge; point at the strip (or click it) to open it again. It stays open while you drag its edge, hold a mouse button or have a drop-down list open.

The panel is hidden on windows narrower than 850 pixels.

## Technical notes

Storage and code: [editor behaviour](../../architecture/editor-behaviour.md#properties-panel). Tests: [validation record](../../validation/2026-11-12-manual-pages.md#properties-panel).
