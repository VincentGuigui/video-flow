# Clip tooltip

Hovering a clip in the clip flow shows a one-line description of it (the browser tooltip of the clip card). Code: `frontend/src/clipTip.ts` (the text), `frontend/src/ui/Flow.tsx` (the card), `frontend/src/ui/useAnalysis.ts` (the analyses).

## Content

- **Video and audio clips:** the summary of the analysis of the clip's source file, cut to about 110 characters: whole sentences while they fit; a short first sentence (a greeting) is completed with the start of the next one, cut at a word boundary with an ellipsis; a first sentence that alone is too long is cut at a word. Without a summary, the first five keywords; without analysis (no speech, analysis skipped, not loaded yet), the clip's name.
- **Audio clips use the same text as the video they come from.** The audio of an imported video is a clip of the same source file, so it has the same analysis and the same tooltip as its video clip. Audio of another file (music, a voice-over) is described by that file's own analysis, or by its name.
- **Image clips and freeze frames:** the clip's name (a freeze frame is named after its clip with “· freeze”).
- **Text clips:** the text of the title on one line.
- **Empty clips:** no tooltip.

The trim handles, the detach button and the other controls on a clip keep their own tooltips.

## Analyses

The flow loads the analysis of each source used by a video or audio clip once (shared with the Transcript tab and the effects). When a source is analysed again from the media menu, or its analysis arrives with an import, the cached analysis is dropped (`forgetAnalysis`) and every tooltip and the Transcript tab show the new one.

## Validation

`frontend/src/clipTip.test.ts` covers shortening (whole sentences, completing a short first sentence, cutting a long one), identical text for video and audio of the same source, the keyword and name fallbacks, and image, text and empty clips. A browser check with a sidecar analysis beside a video found the same description on its video and its audio clip, and the file name on clips without analysis.
