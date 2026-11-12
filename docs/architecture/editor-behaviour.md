# Editor behaviour: rules and code

Precise rules behind the editing pages of the [user manual](../features/README.md): [audio tracks](../features/editing/audio-tracks.md), [compare takes](../features/editing/compare-takes.md), [range and trim](../features/editing/range-and-trim.md), [workspace zones](../features/editing/workspace-zones.md), [properties panel](../features/editing/properties-panel.md), [clip tooltip](../features/editing/clip-tooltip.md) and [project media](../features/import-analysis/media-library.md).

## Audio tracks

- There is no mute control: the per-clip enable checkbox is the only way to silence audio. Disabled audio clips stay visible in their lane and render as silence (TL-09 no longer includes mute).
- **Detach** breaks the link without changing timing. The audio clip then moves, splits and trims on its own (standard audio handles, retained time as in [timeline and clip flow](../features/editing/unified-timeline.md)).
- **Restore original audio** is offered for a video clip whose asset has an audio stream, unless the clip is already linked to audio from its own asset with the same source range. It creates a new audio clip from the video's asset, with the video's source in/out, assembly start and full gain; links it to the video (audio the video was linked to is unlinked and left where it is); leaves every other audio clip untouched, including the detached original audio; and moves the pair to the first free lane at the video's position when the new audio would overlap another audio clip. The whole action is one undoable gesture.

## Compare takes

- The takes of a selected clip are the video clips on any lane that overlap its assembly time, enabled or not, ordered by lane. A selected audio clip stands for its linked video. The toolbar shows **Compare takes (N)** when there are at least two takes.
- The dialog shows one card per take: number, name, duration, a player (preview video; "Preparing the preview video…" until it is ready) and the words spoken inside the take's trimmed range.
- **Sync word**: the first word of the reference take (the first enabled take, else the first) that every take says, preferring words of four or more letters. Words said in one take only are highlighted; the sync word is underlined.
- **Play all** (Space) starts every player 0.5 s before its sync word (or at its trimmed start when there is none) and stops each at its trimmed end. Only one take is audible; the speaker button on a card selects it (default: the reference take).
- **Pick** (or keys 1–9) enables the picked take with its linked audio and disables the other takes with theirs; the pick is one undo step. Several takes may be enabled before a pick; all show as picked. Escape closes the dialog; editor shortcuts are inactive while it is open.
- Not covered: picking a range inside a take (CMP-05) and multicam angles (CMP-06).

## Range and trim

- The range shows as a start and an end marker on the ruler, drawn like the cursor. By default it covers the focused clip plus 2 s before and after (clamped to the edit), or the whole edit when no clip is focused; changing focus resets it. Dragging a marker moves it (at least one frame between start and end) and selects it; scrubbing the timeline or pressing Escape deselects it; Escape with no marker selected leaves clip focus.
- **Space** (and the play button) plays the range once. With a marker selected it plays from 2 s before to 2 s after that marker instead. Playback starts at the cursor when the cursor is inside that window, otherwise at the window start; at the end it stops and the cursor returns to the window start. Space while playing stops.
- In the Transcript tab, clicking a topic sets the range to that topic; collapsing it resets the range. Clicking a word sets the range to that word; Shift+click extends it from the last clicked word. Times outside the clip's trimmed range are ignored.
- **Trim clip to range** keeps only the part of the selected clip inside the range. Its linked audio is trimmed with it, and later clips on every lane move earlier by the removed time (ripple). It is disabled when the range does not shorten the clip. One undo step; the range then returns to its default.
- **Delete / Ripple** act on the explicit range inside the selected clip and linked partner, or on the whole selected clip when no range is selected. Delete preserves time with a gap; Ripple closes the removed span.
- **Auto-trim silence** trims the selected clip to its first and last spoken words, keeping the project clip padding (default 0.15 s before, 0.30 s after), with ripple and linked audio as above. It only shortens, never extends; it needs a transcript and is disabled when there is no speech or nothing to remove.

## Workspace zones

- Four zones: **Project media**, **Timeline**, **Clip flow** and **Editor** (the preview). The zone last clicked is focused and shows a thin teal inner ring. Keyboard shortcuts typed in text fields never act on zones.
- **Ctrl+A** selects every item of the focused zone: all media in Project media; all clips (empty clips excluded) in Clip flow; all enabled clips in Timeline; the clips shown at the cursor in Editor. Picking one clip, or Escape, ends the multiple selection.
- **Delete** lifts the selected clips (their time becomes empty clips) and **Backspace** ripple-deletes them, linked partners included, in one undo step.
- In Project media, a click selects a medium and Ctrl+click adds or removes one. **Delete** or **Backspace** removes the selected media from the project together with every clip that uses them (their time closes up); one undo step restores both. Original files are never touched.
- Thumbnails are scaled to fit the 16:9 thumbnail frame (at most 160×90), so the whole picture is visible: portrait media show with side bands, never cropped.

## Properties panel

The panel layout is a per-viewer preference, remembered in the browser storage of the window (`videoflow.panel`); without storage it starts from the defaults every time. Code: `frontend/src/panel.ts` (layout, bounds, storage), `frontend/src/ui/PropertiesDock.tsx` (frame, controls, resize, folding). Width: 200–640 px, never more than half of the editor area, default 280 px. Unpinned, the panel folds 0.3 s after the pointer leaves it, except while its edge is being dragged, while a mouse button is held, or while one of its drop-down lists is open. It is hidden on windows narrower than 850 px.

## Clip tooltip

Code: `frontend/src/clipTip.ts` (the text), `frontend/src/ui/Flow.tsx` (the card), `frontend/src/ui/useAnalysis.ts` (the analyses). The text is the summary of the analysis of the clip's source file, cut to about 110 characters: whole sentences while they fit; a short first sentence is completed with the start of the next one, cut at a word boundary with an ellipsis; a first sentence that alone is too long is cut at a word. Without a summary: the first five keywords; without analysis: the clip's name. Image clips and freeze frames show their name; text clips the title on one line; empty clips have no tooltip. The audio of an imported video is a clip of the same source file, so it has the same analysis and tooltip as its video. The flow loads the analysis of each source once (shared with the Transcript tab and the effects); when a source is analysed again, the cached analysis is dropped (`forgetAnalysis`) and every tooltip and the Transcript tab show the new one.

## Project media menu

- `GET /api/assets/{id}/info` returns the Info facts; `POST /api/assets/{id}/reveal?target=media|analysis` shows a file (Explorer `/select` on Windows; the containing folder through `xdg-open` on Linux).
- `POST /api/assets/{id}/analyse` starts a re-analysis as an import job that ignores any existing analysis; it is refused while the medium is offline. The sidecar beside the media is overwritten, and the project's cached copy too. Clips already in the edit are kept. When the new analysis matches another clip's media (same rule as on import, see [analysis pipeline](analysis-pipeline.md)) and the medium has a single clip (or one linked pair) in the edit that is not already over that retake, the clip moves onto a new lane at the matched clip's position (one undo step). Several clips of the medium leave the edit unchanged.
- Hovering a media card continuously for two seconds shows its transcribed topic titles; leaving, dragging or scrolling dismisses it; sources without transcribed words and topics show none.
