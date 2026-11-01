# Still images

Pictures (PNG, JPEG, WebP, BMP, TIFF) are imported like video and audio: from Import media, a drop on the window, or a typed path in browser mode. They are referenced in place, never copied or modified.

## Media library

An image becomes an asset whose probe has `still: true`, no duration and no audio stream (`media/ingest.py`, `IMAGE_EXTENSIONS`). Its thumbnail shows **Image** instead of a duration, and its size in pixels. Import does not analyse an image (nothing to transcribe), even when analysis is on. Instead of a video proxy, a PNG preview is made once in the cache (`media/proxy.py`, `build_still_preview`): at most 1920 px on its longest side, transparency kept. The preview and the thumbnails use it, so formats browsers cannot show (TIFF) and very large photos work too.

## In the flow

Importing an image appends a 3 s **image clip** at the end of the flow, like a video clip without audio. An image clip is a video clip with `stillFrame: 0`:

- `stillFrame` (`EditorClip.still_frame`) is the source frame a still clip shows for its whole length. A clip with a `stillFrame` is a **still clip**; `null` means a moving clip. Only video clips at speed 1 can be still. [Freeze frames](../roadmap.md) use the same field with a frame of a video.
- A still clip has no source limit. Both edges trim freely, longer or shorter, with the usual ripple and preserve-time handles, and it snaps like any clip. Its source range only measures its length and always starts at 0 (like text clips); splitting it gives two still clips of the same picture.
- A dissolve onto or from a still clip always has the handles it needs: the picture repeats.
- Speed does not apply to still clips (the Speed effect is not offered). Fades, transitions, zoom & pan, transform, crop and backgrounds work as on video clips.
- An image asset accepts only still clips; validation refuses a moving clip on it (`editor/resolve.py`).

Clip properties name it **Image clip** with its duration and no source range, Transcript tab or link selector.

## Preview, render and exports

- **Preview:** the clip box shows the PNG preview as a picture (`ui/Preview.tsx`, `Picture`); a still clip of a video shows its video paused on the held frame.
- **Render:** the graph takes the held frame (for an image, its only frame; for a video, frame `stillFrame` after resampling to the project rate), loops it for the clip's frames and places it like any video clip (`render/graph.py`).
- **Camtasia:** an image clip is an `IMFile` (one picture, `mediaDuration` 1) whose source-bin entry has a single picture track (type 1, range [0, 1]), as Camtasia writes them. A template without an image clip falls back on the built-in structure, with a warning.
- **OTIO:** the clip references the image without an available range; its `stillFrame` is in the clip metadata. EDL, SRT and paper edit treat it as a video event without words.

## Validation

- `backend/tests/render/test_still_images.py`: images import as still assets; still clips have no source limit and image assets need still clips; a render of a red clip dissolving into a 4 s image (longer than any source) has the right frames, the mixed colours at the cut and the image at the end; a still clip of a video renders its held frame for its whole length; Camtasia writes an `IMFile` with a picture track; every export format accepts still clips.
- `backend/tests/editor/test_api.py::test_image_import_adds_a_three_second_still_clip_with_a_png_preview`.
- `frontend/src/still.test.ts`: trimming past any source on both edges, split keeping the held frame, speed refused, full dissolve handles.
- A browser check imported a PNG and a JPEG (Image thumbnails, image clips of 3 s), showed the picture in the preview and extended the image clip on both edges past its one-picture source.
