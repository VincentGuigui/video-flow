# Render and export

Click **Export** to render the edit or hand it over to another editor. Exports are saved in the project's `exports` folder.

## MP4 video

**Save as MP4 video** renders every enabled clip, lane and sound into one video, with the transitions, effects, keyframes and titles, exactly as the preview shows them. Before starting, choose:

- **Full resolution** or **Draft preview** (smaller and faster, to check an edit);
- **Normalize audio**: brings the loudness to a standard level.

The render shows its progress and can be cancelled. When it is done, a save window asks where to put the video. Your original media are never overwritten.

## Other editors and files

| Export | What you get |
|--------|--------------|
| **OTIO timeline** | An OpenTimelineIO file of the cuts and lanes, for editors that read OTIO |
| **Portable OTIOZ** | The same timeline and the original media in one archive |
| **EDL + paper edit** | A CMX 3600 edit list of the main lane, and a Markdown and CSV list of the clips with their transcript |
| **Subtitles** | An SRT file from the transcribed words |
| **Camtasia project** | A `.tscproj` with clips, lanes, transitions and titles ([Camtasia export](camtasia-export.md)) |

Gain, fades and picture placement are carried as metadata in OTIO, which other editors may ignore; use the MP4 video to get the edit exactly as you see it.

## Technical notes

The render compiles the edit into FFmpeg filter graphs from the original media, uses hardware encoders when available and validates frames and duration before publishing the file. What each format carries and loses is listed in [render and export](../../architecture/render-export.md).
