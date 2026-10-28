# 20. Features inspired by the user's Camtasia projects — 2026-10-28

Four real Camtasia projects were analysed (RayNeo IO review 1920×1080 21 min, ArtCapital debrief 1080×1080 44 s, TangrIAm teaser 1920×1080 made with Camtasia 2020, demo 11 s). They are not stored in the repository.

## Findings

| Usage | Observed | Decision |
|-------|----------|----------|
| Transitions | Fade 26 of 34 (13 one-sided: fade in at a clip's start or out at its end, 0.5–1 s), SphericalSpin 8, Glitch 2 | Keep fades only; add one-sided edge fades |
| Clip speed | 21 clips: 1/3, 2×, fit-to-duration ratios | Add clip speed |
| Zoom & pan | 21 animated zooms on details (in ≈0.3 s, hold, out ≈1 s), keyframes on scale/translation | Add zoom & pan animation |
| Volume keyframes | 60, mostly ranges muted or lowered | Add mute a range; music with ducking |
| Background music | Separate audio track at ≈71 % volume | Add music lane with ducking under speech |
| Text | 4–43 callouts per project (text, text in rectangle) | Add titles and lower thirds |
| Freeze frames | ≈100 one-frame image holds | Not selected for now |
| Blur region | 14 in one project | Not selected for now |
| Canvas | 16:9 and 1:1 | Already supported |
| Camtasia versions | 2023.4.3 (format 7.0) and 2020 (format 4.0) | Export targets 2023.4 and newer only |

## Backlog, in order

1. **Edge fades**: fade in from black at a clip's start, fade out to black at its end, with audio fades. Camtasia: one-sided `Fade` transition.
2. **Clip speed**: slow or fast playback of a clip, preserving audio pitch. Camtasia: `scalar`.
3. **Zoom & pan**: animated zoom on a region of a clip and back. Camtasia: keyframes on `scale0/1` and `translation0/1`.
4. **Music and ducking**: background music lane with its own volume and fades, lowered automatically under transcribed speech. Camtasia: AMFile with volume keyframes.
5. **Mute a range**: silence part of a clip from the range selector without cutting the picture. Camtasia: volume keyframes.
6. **Titles and lower thirds**: text cards and lower thirds composited by FFmpeg. Camtasia: text `Callout`.

Each feature covers the editor, preview, MP4 render and Camtasia export, and gets its own section in a dated spec revision when built.
