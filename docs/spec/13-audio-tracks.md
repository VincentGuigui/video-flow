# 13. Audio tracks of video clips — 2026-10-26

This revision supplements 09 and 12. It sets the audio rules for clips imported with both picture and sound.

- **No mute control.** The per-clip enable checkbox is the only way to silence audio. Disabled audio clips stay visible in their lane and render as silence. TL-09 no longer includes mute.
- **Detach.** Detach (chain button in the flow, or Detach audio & video in Properties) breaks the link without changing timing. The audio clip then moves, splits and trims on its own (standard audio handles, retained time per 12).
- **Restore original audio.** For a video clip whose asset has an audio stream, Properties shows Restore original audio unless the clip is already linked to audio from its own asset with the same source range. The action:
  1. creates a new audio clip from the video's asset, with the video's source in/out, assembly start and full gain;
  2. links it to the video. If the video was linked to other audio, that audio is unlinked and left where it is;
  3. leaves every other audio clip untouched, including the detached original audio, which the user can disable or delete;
  4. moves the pair to the first free lane at the video's position when the new audio would overlap another audio clip.

  The whole action is one undoable gesture.

Validation: model tests cover availability (hidden when already linked to its own audio, hidden for audio clips), aligned source range, link creation, and that existing audio clips keep their position.
