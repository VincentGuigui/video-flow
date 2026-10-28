# 21. Clip effects — 2026-10-28

Features from the backlog in [20](20-camtasia-inspired-backlog.md), one section each. They apply to the editor, preview, MP4 render and Camtasia export.

## Edge fades

- Each clip has `fadeIn` and `fadeOut` (frames, default 0). Clip properties → **Fades** sets them in seconds; linked video and audio get the same values.
- Picture: the clip's opacity ramps from 0 at its start over `fadeIn` frames and to 0 over its last `fadeOut` frames. A clip on the bottom lane therefore fades from/to black; a clip over other lanes fades from/to what lies below. Audio: volume ramps from/to silence over the same frames.
- Fades are capped at the clip length, combine with transitions (the longer fade wins on an edge) and survive splits: the left part keeps the fade-in, the right part the fade-out.
- Render: alpha `fade` on the clip and its backdrop, `afade` on its audio. OTIO: audio fades on audio clips (metadata for other tools). Camtasia: a one-sided `Fade` (only `rightMedia` for a fade-in, only `leftMedia` for a fade-out), skipped where a transition already uses that edge.

Validation: backend tests cover planning, capping and merging with a dissolve; a real render checks black → red → black ramps at five frames; the Camtasia test checks one-sided fades and no duplicate on a transition edge. Frontend tests mirror the planning, opacity at both edges and split behaviour. A browser check set a 1 s fade-in, saw it saved on both linked clips and the preview go from opacity 0 to 1.
