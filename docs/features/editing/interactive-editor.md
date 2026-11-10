# Editor workspace

The editor is one window with five areas:

| Area | Where | What it is for |
|------|-------|----------------|
| **Header** | Top | The logo (back to the project home), save state, Settings, undo/redo, **Import media**, **Save**, **Export** |
| **Project media** | Left | The imported media of the project ([project media](../import-analysis/media-library.md)) |
| **Preview & editor** | Centre, top | Plays the edit and lets you place, scale and crop the selected clip |
| **Properties** | Right | Settings of the selected clip or of the project ([properties panel](properties-panel.md)) |
| **Timeline and clip flow** | Bottom | The edit itself: the ruler, the cursor and the clips on their lanes ([timeline and clip flow](unified-timeline.md)) |

The status bar at the bottom shows the length of the edit, the interface zoom and the running Video-Flow version.

## Playing the edit

The playback controls sit above the preview: beginning, back 10 s, 1 s and one frame, play/pause, forward one frame, 1 s and 10 s, end. **Space** plays the timeline range ([range and trim](range-and-trim.md)). Drag the cursor on the ruler to scrub.

The preview shows every enabled video clip at the cursor, the highest lane on top, and plays every enabled audio clip together.

## Placing a picture

Double-click a clip to focus it (see [timeline and clip flow](unified-timeline.md#focusing-a-clip)); the preview then shows handles around its picture:

- **Scale** mode: drag inside the picture to move it, drag a handle to resize it. The aspect ratio is kept; hold **Shift** to stretch, **Alt** to move opposite edges together.
- **Crop** mode: drag a handle to crop that edge.
- Edges snap to the centre and the sides of the frame, and guides show where.
- **Background** sets what fills the frame around the picture: transparent (the lanes below, or black), a colour, or the picture itself blurred to fill the frame.
- In the Clip tab, X, Y, Width and Height can be typed (the preview follows as you type), and **Scale to fit / Scale to fill** fits the whole picture in the frame or fills the frame with it.

Animated position, size, rotation, crop and opacity are set with [keyframes](../finishing/keyframes.md).

## Output resolution

The **Project** tab of the properties sets the output resolution: landscape, portrait and square formats with their ratio. Changing it keeps every picture's proportions and centres the old frame in the new one; going back to the previous format restores the clips' original size.

## Keyboard

| Action | Keys |
|--------|------|
| Play the range / pause | Space |
| One frame · one second · ten seconds | ← / → · Shift + ← / → · Ctrl + ← / → |
| Beginning / end | Home / End, or Ctrl + Shift + ← / → |
| Leave clip focus | Esc |
| Split at the cursor | S |
| Freeze frame at the cursor | F |
| Keyframe at the cursor | K |
| Delete, keeping the time | Delete |
| Ripple delete | Backspace |
| Select all in the zone last clicked | Ctrl + A |
| Undo / redo | Ctrl + Z / Ctrl + Shift + Z |
| Zoom the timeline around the pointer | Ctrl + wheel |
| Scroll the timeline | Shift + wheel |

**?** (or **Keyboard shortcuts** at the bottom of Project media) shows the list. Keys typed in a text field act on the field only.

## Interface zoom and menus

The minus / percentage / plus controls in the status bar zoom the whole interface (click the percentage to go back to 100 %); they do not change the timeline zoom. Right-click shows only the app's own menus.

## Saving

Every change is saved at once. **Save** names an untitled project; its arrow offers **Save as**. See [projects](../getting-started/projects.md) for where projects live.

## Technical notes

The edit is the `editor` document of `project.json` ([data model](../../architecture/data-model.md)); every change is one `SetEditor` command and one undo step. The window is a PySide6 / Qt WebEngine host around the React interface, talking to a local, authenticated API ([desktop shell](../../architecture/desktop-shell.md)). Frame arithmetic uses the project's rational frame rate.
