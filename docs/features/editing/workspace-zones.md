# Selecting and deleting: workspace zones

The [editor workspace](interactive-editor.md) has four zones: **Project media**, **Timeline**, **Clip flow** and the **Editor** (the preview). The zone you clicked last is the active one and shows a thin teal ring. Select-all and delete act on that zone. Keys typed in a text field never act on a zone.

## Select all (Ctrl + A)

| Zone | Selects |
|------|---------|
| Project media | Every medium |
| Clip flow | Every clip (empty clips excluded) |
| Timeline | Every enabled clip |
| Editor | The clips shown at the cursor |

Selected clips are highlighted in the flow and the timeline, and the properties panel shows how many are selected. Clicking one clip, or **Esc**, ends the multiple selection.

## Removing clips

- **Delete** lifts the selected clips: their time stays as empty clips.
- **Backspace** removes them and closes the gap. Linked audio goes with its picture.

One undo step each.

## Removing media

In Project media, click a medium to select it, **Ctrl + click** to add or remove one. **Delete** or **Backspace** removes the selected media from the project **together with every clip that uses them**, and later clips close up; one undo step brings everything back. Your original files are never touched.

## Thumbnails

Media thumbnails fit entirely in a 16:9 frame: portrait media show with side bands, never cropped.

## Cache

**Settings → Cache** shows the total size of the cache and one line per project. The cache holds what Video-Flow can rebuild (previews, thumbnails, waveforms, title pictures, render work files), so it can be cleared freely. **Open cache folder** shows it in your file manager; **Clear cache** deletes it (not while an import or a render runs; files in use are kept and listed).

## Technical notes

Rules: [editor behaviour](../../architecture/editor-behaviour.md#workspace-zones), [cache folder](../../architecture/projects-and-setup.md#cache-folder). Tests: [validation record](../../validation/2026-11-12-manual-pages.md#workspace-zones-and-cache).
