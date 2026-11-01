# Workspace zones, selection and cache — 2026-11-01

This revision supplements [interactive editor](interactive-editor.md) and [editor refinements](editor-refinements.md).

## Zones

- The workspace has four zones: **Project media** (the media list), **Timeline** (the assembly timeline), **Clip flow** and **Editor** (the preview). The zone last clicked is the focused zone; it shows a thin teal inner ring. Keyboard shortcuts typed in text fields never act on zones.
- **Ctrl+A** selects every item of the focused zone: all media in Project media; all clips (empty clips excluded) in Clip flow; all enabled clips in Timeline; the clips shown at the cursor in Editor. Selected clips are highlighted in the flow and the timeline, and the clip properties panel shows how many are selected. Picking one clip, or Escape, ends the multiple selection.
- **Delete** lifts the selected clips (their time becomes empty clips) and **Backspace** ripple-deletes them, linked partners included, in one undo step.
- In Project media, a click selects a medium and Ctrl+click adds or removes one. **Delete** or **Backspace** removes the selected media from the project together with every clip that uses them (their time closes up); one undo step restores both. Original files are never touched.

## Media thumbnails

Thumbnails are scaled to fit the 16:9 thumbnail frame (at most 160×90), so the whole picture is visible: portrait media show with side bands, never cropped.

## Cache folder

Settings → **Cache** shows the project's cache directory (proxies, thumbnails, waveforms, title pictures and render work files) and **Open cache folder** opens it in the system file manager (Explorer on Windows, the default file manager through `xdg-open` on Linux).

Validation: frontend tests cover the items of each zone, removing several clips with partners (lift and ripple) and removing media with their clips; a backend test covers the cache path and the open request. A browser check selected all six clips of the flow with Ctrl+A and deleted them, undid it, removed one medium (and its two clips) and undid it, selected all media with Ctrl+A, measured the three thumbnails (portrait included) fully inside their frames, and opened Settings with the cache path and button.
