# Clip tooltip

Hover a clip in the clip flow to see a one-line description of it.

## What it says

- **Video and audio clips:** the summary of the clip's file, shortened to about one line. A short first sentence (a greeting) is completed with the start of the next one. Without a summary, the first keywords; without any analysis (no speech, analysis skipped), the clip's name.
- **The audio of a video says the same as its video.** Both come from the same file, so they share its analysis. Audio from another file (music, a voice-over) is described by its own analysis, or by its name.
- **Image clips and freeze frames:** the clip's name.
- **Titles and lower thirds:** their text on one line.
- **Empty clips:** no tooltip.

The trim handles, the detach button and the other controls on a clip keep their own tooltips.

## Staying up to date

When you analyse a medium again ([project media](../import-analysis/media-library.md)), or an import brings its analysis, the tooltips and the Transcript tab show the new analysis at once.

## Technical notes

Rules and code: [editor behaviour](../../architecture/editor-behaviour.md#clip-tooltip). Tests: [validation record](../../validation/2026-11-12-manual-pages.md#clip-tooltip).
