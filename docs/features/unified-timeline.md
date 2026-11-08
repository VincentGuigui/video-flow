# Unified timeline and focused editing — 2026-10-26

This revision supersedes conflicting editing details in [interactive editor](interactive-editor.md) and [editor refinements](editor-refinements.md); the native desktop architecture in [desktop shell](../architecture/desktop-shell.md) remains authoritative.

- The assembly timeline is the only ruler and cursor. Its zoom/fit controls sit at the right of its header. The flow is a clip-lane editor driven by the same scale and horizontal scroll, with no independent ruler, cursor, zoom control or focus banner. Double-clicking a clip fits the assembly range to that clip plus up to two seconds of context. Back to full edit [Esc] appears beside Clip timeline. The scrub hint sits beside the Space hint; the flow footer retains interaction hints without Video/Audio/Enabled legends.
- Remove the Linked audio text and broken-chain decoration from clip cards. The existing full-chain detach control remains available.
- Properties offers Link audio / Link video for separate clips sharing assembly start and duration. Source offsets may differ. Linking preserves each source offset; linked movement, splitting and trimming remain paired. Incompatible ranges cannot be silently retimed by linking. Detach remains available in properties.
- Audio has one standard handle per edge. Trimming adjusts media bounds and retains the previously occupied assembly span without inserting a fake silence clip or shifting later clips. Retained time is stored as validated heldRange metadata on the clip and resolves to black/silence when no active media covers it. Disabling/removing that clip removes its retained span; lift preserves the occupied span with an authored gap. Source bounds still apply to both members of linked pairs.
- Remove Independent clip / Linked video + audio labels. Collapse Source range by default. Transform X/Y/width/height inputs update the preview during typing; persistence coalesces changes and retains edits entered while a save is in flight. Save, Save as, export and undo flush pending property changes. Scale to fit / Scale to fill moves to the bottom of the Transform block.
- Scale and crop handles snap visible picture edges to the top, left, bottom and right viewport edges. Respect ratio locking, Shift stretching and Alt symmetry, and display guides at the actual snapped edges.

Validation includes linking different source offsets, paired splits, normal audio trimming with retained time, persistence/export of retained silence, rapid property updates during asynchronous saves, shared pointer-centered zoom, and edge snapping with modifiers. The real Qt smoke check covers the unified axis, collapsed source properties, live numeric input, detach/relink and standard audio handles, followed by MP4 rendering and project copying.

## Current interaction details

- Double-click assembly clips to focus their edit

- Show transcribed media topics after two seconds of hover

- Map transcript text selections onto the timeline range

- Correct transcript words in place and persist analysis JSON

- Set output resolution from Project properties

- Place playback controls above the video preview

- Place clip actions and clip count below the flow

- Merge timeline and clip flow with continuous cursor and range guides

- Delete or ripple the selected range before falling back to whole clips

- Move range trimming and silence trimming into the flow toolbar

- Remove the redundant Delete range action from clip properties

- Show Compare takes in the flow toolbar for parallel takes

- Render a held-edge dissolve when source handles are exhausted

- Preserve transcript corrections when source folders are read-only

Current interaction details:

- Align range guides across the merged timeline workspace
