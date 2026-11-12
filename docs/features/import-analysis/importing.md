# Importing media

## Adding files

Click **Import media**, or drop files on the window. Video, audio and still images are accepted ([still images](still-images.md)). The files stay where they are: Video-Flow references them in place and never copies or changes them.

The import window offers two choices for the batch:

- **Analyse & group similar takes**: transcribe each file, write a summary, keywords and topics, and stack the file over the retake it matches.
- **Import only**: add the files without analysis (you can analyse a medium later from its menu, see [project media](media-library.md)).

**Analyse new imports by default** in Settings decides which one is preselected.

## Following the import

Files are processed one at a time. The window shows each file's name and progress, and which file of the batch is running. **Cancel this file** skips the file being processed, including its transcription; cancelling the batch stops that file and the ones after it. A file that fails does not stop the others, and files already imported stay in the project.

Each imported file is added to the edit at once: after the last clip, or stacked on a new lane over the retake it matches ([retake grouping](retake-grouping.md)). Stacking is a suggestion: move the clip if it is wrong. Files without speech import normally, with an empty transcript.

The first analysed import may need AI models: the import then waits, and the models window opens so you can download them ([AI models and components](../getting-started/ai-models.md)).

## Preview media

Video-Flow never plays your originals directly: it makes a light preview of each file, in two steps, so you can start editing at once.

1. **Right after import**, in a second or two per minute of footage: one picture per second and the sound. The clip already shows in the preview and plays its real sound; the picture changes once per second.
2. **In the background**, one file at a time and at low priority so the editor stays fluid: a smooth preview video. As soon as it is ready, the preview uses it and the pictures of step 1 are deleted.

The media list shows the state of each file: **Preview 40%** while its video is being made, **Preview queued** while it waits, **Ready** when done, **Preview failed** (hover for the reason) if the video could not be made; the pictures and sound remain usable then. Compare takes waits for the preview videos. A file you are looking at moves to the front of the queue.

Previews are part of the rebuildable cache ([workspace zones](../editing/workspace-zones.md)): clearing the cache makes them again. Still images and WAV, MP3, FLAC, OGG or Opus audio play as they are and need none. The render always uses the originals.

## Analysis files

The analysis of a file is saved next to it as a JSON file with the same name (`take-01.json` for `take-01.mp4`; `take-01.mp4.json` is read too) (words with their times, summary, keywords, topics). An existing compatible file is reused without loading any model, which also lets you share analyses with the media. When the media folder is read-only, the analysis is kept in the project cache instead. Video-Flow never overwrites a JSON file that is not its own analysis of that medium.

Summaries and keywords come from the engine chosen in Settings: a simple built-in method, or the local Qwen model. Transcription uses Parakeet or Whisper. When transcription fails, the import says so; no text is invented.

## Technical notes

Imports run in a sequential, cancellable queue (`editor/imports.py`), including the transcription and model work in worker processes. The analysis JSON (version 1) holds integer-microsecond word times and a fingerprint of the source; it is written atomically. Native drops and the file picker hand the backend scoped grants for the chosen files, never their content ([desktop shell](../../architecture/desktop-shell.md)). See [analysis pipeline](../../architecture/analysis-pipeline.md). Preview media are described in [desktop shell](../../architecture/desktop-shell.md#media-playback) and tested in the [preview media validation](../../validation/2026-11-12-preview-media.md).
