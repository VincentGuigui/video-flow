# Validation: editing, import, project and still-image features

Tests and checks that used to sit at the bottom of the manual pages. Behaviour is in the [user manual](../features/README.md); rules and code are in [editor behaviour](../architecture/editor-behaviour.md), [analysis pipeline](../architecture/analysis-pipeline.md), [projects, cache and FFmpeg](../architecture/projects-and-setup.md) and [transitions, effects, titles, keyframes and still clips](../architecture/effects-and-titles.md).

## Audio tracks

Model tests cover availability of Restore original audio (hidden when already linked to its own audio, hidden for audio clips), aligned source range, link creation, and that existing audio clips keep their position.

## Compare takes

Frontend tests cover take detection (disabled takes, audio selection, overlap), pick enable/disable with linked audio, sync word choice (long-word preference, accents, none) and divergent words. A browser check imported two analysed takes, opened the view from clip properties, verified synced playback with one audible take, divergent highlights, pick with key 2 and Escape.

## Range and trim

Frontend tests cover the default range, the window around a marker, playback start, marker ordering, trim to range with linked audio and ripple, delete range (middle cut, edge trim, refusals), auto-trim padding and no-speech. A browser check on a served project confirmed marker drag and selection, playback around a marker with return to the window start, word selection, trim, undo and auto-trim.

## Workspace zones and cache

Frontend tests cover the items of each zone, removing several clips with partners (lift and ripple) and removing media with their clips; a backend test covers the cache path and the open request. A browser check selected all six clips of the flow with Ctrl+A and deleted them, undid it, removed one medium (and its two clips) and undid it, selected all media with Ctrl+A, measured the three thumbnails (portrait included) fully inside their frames, and opened Settings with the cache path and button.

## Properties panel

`frontend/src/panel.test.ts` covers the width bounds and reading a stored layout (defaults, invalid data). A browser check resized the panel, switched to tall, unpinned it, saw it fold into the strip when the pointer left and open again on the strip, switched back to half while unpinned, and found the layout stored.

## Clip tooltip

`frontend/src/clipTip.test.ts` covers shortening (whole sentences, completing a short first sentence, cutting a long one), identical text for video and audio of the same source, the keyword and name fallbacks, and image, text and empty clips. A browser check with a sidecar analysis beside a video found the same description on its video and its audio clip, and the file name on clips without analysis.

## Project media menu

A backend test covers the info facts before and after an analysis exists, revealing the media and its JSON, and a re-analysis that does not reuse the existing JSON. A browser check opened the menu, the Info dialog (size, duration, relative path, analysis summary), Show transcript, and started a re-analysis that transcribed again instead of reusing the JSON.

## Retake grouping

Unit tests cover matching and non-matching clips, partial retakes, the effect of vectors on a borderline lexical match, the vector cache, and the word-overlap threshold on the benchmark (≥ 95 %). A smoke test checks the MiniLM blend on the benchmark (≥ 97 %; measured 100 %). An API test imports a take, an unrelated clip and a retake, and checks that the retake is stacked over the take.

## Transcript panel

Backend tests cover sentence splitting, two-subject segmentation with timecodes, single-subject stability, title length and LLM fallback, summary length and topics derived for old sidecars. Frontend tests cover source-to-assembly mapping with trims, disabled clips and range clamping. A browser check on a served project confirmed topics, expansion, range selection and cursor seeks.

## Projects

Backend tests cover folder naming, Save as beside the original with relative media, rename moving the folder and updating the list, the recent list order and removal (files kept), media following a copied working folder, native folder handles (desktop secret required, single use, project folders only for Open), close and reopen. A browser check created a project in one working folder, imported media (stored as `talk.mp4` relative), created a second project in another folder from the home page, reopened the first by its folder, and listed both caches in Settings.

## FFmpeg setup

- `tests/media/test_caps_cache.py`: one probe per build across launches, a new probe for a changed build or a damaged cache file.
- `tests/media/test_ffmpeg_install.py`: zip and tar.xz unpacking with licence files, checksum mismatch, platforms, scripts pinning the same builds.
- `tests/editor/test_api.py::test_ffmpeg_status_and_consented_install`: status, install job, no pinned build.
- Checked by hand on Linux x64: real download from the app window and from `scripts/install.sh`.

## Still images and freeze frames

- `backend/tests/render/test_still_images.py`: images import as still assets; still clips have no source limit and image assets need still clips; a render of a red clip dissolving into a 4 s image (longer than any source) has the right frames, the mixed colours at the cut and the image at the end; a still clip of a video renders its held frame for its whole length; Camtasia writes an `IMFile` with a picture track; every export format accepts still clips; freeze frames in OTIO (`FreezeFrame` effect), EDL (read back as a freeze by OTIO's CMX reader) and Camtasia (`IMFile` at the frozen frame).
- `backend/tests/editor/test_api.py::test_image_import_adds_a_three_second_still_clip_with_a_png_preview`.
- `frontend/src/still.test.ts`: trimming past any source on both edges, split keeping the held frame, speed refused, full dissolve handles; freeze inside a linked clip (split, silent audio lane, ripple), on the first frame (before, with the incoming transition) and the last (after, with the outgoing one), and refused on still clips or outside the clip.
- A browser check imported a PNG and a JPEG (Image thumbnails, image clips of 3 s), showed the picture in the preview and extended the image clip on both edges past its one-picture source, then pressed F 1 s into a video clip: it was split around a 3 s freeze of frame 30 and the rest moved later.

## Keyframes

- `backend/tests/render/test_keyframes_render.py`: interpolation (hold, linear, smooth, sorting) and the piecewise expression; renders of an opacity fade over a lower clip, an animated crop revealing the clip below, and a 45° rotation (centre, corners and tips of the box).
- `backend/tests/render/test_transitions_render.py::test_keyframes_magnify_toward_the_left_edge_and_return`: a 400 % push-in on the left edge and back, with exact frames.
- `backend/tests/exporters/test_camtasia.py::test_keyframes_become_camtasia_keyframes_in_media_time`.
- `frontend/src/keyframes.test.ts`: interpolation, auto-key, add, move within the visible range, remove (the last one becomes the transform), clear, visible keyframes and still-clip head trims.
- A browser check added two keyframes on an image clip (the second at 50 %, 30°, 60 % opacity), saw the preview halfway between them and the diamonds on the timeline and the flow card.
