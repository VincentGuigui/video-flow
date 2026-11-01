# 17. Transitions in the interactive editor — 2026-10-26

This revision implements TR-01, TR-02, TR-04, TR-06 (shortening only) and TR-07 of 02 §4.6, and PRV-02 for these types, for the editor document of 09. It replaces the legacy `Transition` entity of 05 for interactive edits.

## Model

- The editor document has `transitions`: `{id, leftId, rightId, type, duration}`, with `type` one of `dissolve`, `dip_black`, `dip_white` and `duration` in project frames (requested, centred on the cut). Cut = no transition.
- A transition is **active** when both clips exist, are enabled video clips on the same lane, and the left clip ends exactly where the right clip starts in the assembly. Otherwise it is dormant: kept, ignored by preview, render and export, and never an edit error. Splitting the left clip keeps the transition on the cut after the right part.
- Total duration is unchanged by any transition.

## Behaviour

| Type | Picture | Audio (linked audio follows, TR-04) | Handles |
|------|---------|--------------------------------------|---------|
| Cross dissolve | The left clip continues `after` frames past the cut and the right clip starts `before` frames early (`before` = ⌊T/2⌋, `after` = T − `before`), fading in over the left. | Crossfade over the overlap. | Uses source media beyond the cut. |
| Dip to black / white | The whole picture fades to the colour over `before` frames and back over `after` frames. | Left audio fades out over `before`, right fades in over `after`. | None. |

When the source has too few frames beyond the cut, or a clip is shorter than its half, the transition is **shortened** (TR-06) and a warning is shown in clip properties and in the render log. Changing alignment is not offered.

## UI

- Clip properties of a video clip show **Transitions**: one row per cut with an adjacent clip (*In · from …*, *Out · to …*), a type selector (Cut, Cross dissolve, Dip to black, Dip to white) and the duration in seconds. New transitions use the project default duration (0.5 s). **Apply … to all cuts** applies the shown type and duration to every cut between adjacent video clips (TR-07).
- The assembly timeline marks each active transition over its frames.
- The preview approximates dissolves with opacity, dips with a colour layer, and audio fades with volume (PRV-02).

## Render and export

- The MP4 render follows the table above exactly (alpha fade of the incoming clip and its backdrop, colour overlay for dips, `afade` on linked audio).
- OTIO and EDL receive transitions on the V1 lane (dissolve as `SMPTE_Dissolve` / `D`, dips as custom with Video-Flow metadata; EDL writes them as dissolves). Transitions on higher lanes are rendered but not exported, and audio crossfades are not written; both are reported as warnings.
- Overlay windows in the render graph use timestamps rather than frame counters, so every clip of a lane renders after a cut (a defect fixed with this revision).

Validation: backend tests cover the plan (handles, shortening, dips, dormant cases) and real renders of each type with exact frame counts and pixel checks at the cut, plus a regression test for sequential clips on one lane. Frontend tests mirror the plan, cover setting, replacing, removing and applying to all cuts, splits, dip opacity and audio gain. A browser check added a dissolve after Delete range, changed its duration, checked the timeline marker, and rendered an MP4 whose frame count matched the timeline.
