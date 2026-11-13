# Command line

The `videoflow` command (from `backend/` with `uv run videoflow`, or the packaged executable) opens the app and exports projects without the window.

| Command | What it does |
|---------|--------------|
| `videoflow` or `videoflow desktop [--project PATH]` | Opens the desktop app, on the given project folder (created if missing) or the last one |
| `videoflow serve --project PATH [--port N] [--media-root DIR]` | Browser diagnostic mode on a local port |
| `videoflow export PROJECT [formats] [options]` | Exports a project, see below |
| `videoflow version` | Prints the version |

## Export

```powershell
uv run videoflow export C:\Rushes\demo.video-flow --otio --edl --paper-edit
uv run videoflow export C:\Rushes\demo.video-flow --otioz
uv run videoflow export C:\Rushes\demo.video-flow --srt --transcripts words.json
uv run videoflow export C:\Rushes\demo.video-flow --camtasia
```

The input may also be a `project.json` file. With no format flag, export writes OTIO. Files go to the project's `exports/` folder, or `--output DIRECTORY`; `--overwrite` replaces existing files. Each run writes `edit.report.json` with resolver warnings and format limitations. `--include-alternates` adds a disabled track to OTIO/OTIOZ for every disabled video clip (an unpicked take), at its position.

SRT takes a JSON object mapping asset IDs to transcript objects, for example:

```json
{"ast_example": {"words": [{"text": "Bonjour.", "startUs": 1200000, "endUs": 1800000}]}}
```

Word times refer to the original source. Subtitles follow the audible cut, including replacement audio and transcript corrections; fillers are removed. Cues stay within clip boundaries, have up to two 42-character lines, and extend to one second when space permits. Transcript corrections lack word timings and are distributed within their authored range. Paper edits can be exported without transcripts.

OTIO keeps exact transition definitions, editing identifiers and clip settings as Video-Flow metadata; other editors may ignore gain, fades, fit and freeze handles. OTIOZ copies the source media and requires every referenced file to exist. EDL contains V1 only, uses eight-character reels with a mapping file, and approximates other transitions as dissolves.

Camtasia: to match your Camtasia version exactly, copy any project saved by it to `templates/camtasia.tscproj` in the application folder (or pass `--camtasia-template PATH`); its structures are cloned, its content is not. Crop, backgrounds and transition audio crossfades are not exported (see the export report and [Camtasia export](../features/output/camtasia-export.md)).
