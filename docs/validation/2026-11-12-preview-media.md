# Validation: preview media

Behaviour: [importing media](../features/import-analysis/importing.md#preview-media). Rules: [desktop shell](../architecture/desktop-shell.md#media-playback).

## Bench

60 s of 1080p H.264 on 4 cores. Previous path: H.264 proxy 8.3 s, then WebM 7.9 s, before a clip could play. Now: stills from keyframes only 0.6 s (3.3 s with a full decode) and Opus sound 0.6 s, in one run; the WebM made directly from the source takes 10.2 s in the background at low priority.

## Tests

`backend/tests/editor/test_previews.py` covers the quick pass (one still per second, clamped indices, Opus sound), the background video replacing it (VP9/Opus, quick-pass folder deleted), queue order and priority, reuse of earlier WebM files, sources that play as they are (WAV, images; AAC does not), and the API: stills, sound and thumbnail served while the video is being made, then the WebM once ready. `frontend/src/previews.test.ts` covers the media and still URLs and when a clip is playable.

## Browser check

A served project with a 90 s 1080p clip and an empty cache: the clip showed the still of the cursor second within a second of opening, the media list read "Preview 14%", and the `<video>` replaced the still when the preview was ready (12.7 s), playable (readyState 4).
