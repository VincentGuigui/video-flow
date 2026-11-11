# Clip effects, titles and lower thirds

Effects are added to a clip from the **Effects** tab of the properties panel. Select a clip, open the tab and click **Add effect**: the list shows the effects that fit this clip, with a short description. Each effect in use is a card with its name, a one-line summary (for example "0.50 s" or "200 %"), a fold arrow and a **×** that removes the effect. For a video clip, the transitions of its two cuts come first ([transitions](transitions.md)). Animation (position, size, rotation, crop, opacity) has its own tab ([keyframed transforms](keyframes.md)). Empty clips have no effects.

## Fades

**Fade in** and **Fade out** make the picture and the sound of a clip appear from, or disappear to, nothing. Add the card, then set its **Duration** in seconds (new fades last 0.5 s). A clip on the bottom lane fades from or to black; a clip over other lanes fades from or to what lies below. Linked video and audio fade together. A fade can't be longer than the clip, and a transition on the same edge uses the longer of the two. When you split a clip, the first part keeps the fade-in and the second part the fade-out.

## Speed

**Speed** plays a clip faster or slower, from 25 % to 400 %; the sound keeps its pitch. Pick a preset, or use **Fit to range** to set the speed so the clip exactly fills the timeline range ([range and trim](../editing/range-and-trim.md)). The clip gets shorter or longer and later clips move; linked video and audio always share one speed. Image clips and freeze frames have no speed.

## Mute ranges

**Mute ranges** silences part of a clip's sound while keeping its picture. Set the timeline range, then click **Mute timeline range**: the card lists each muted range with its timecodes and a **×**. Muted words are left out of the SRT subtitles and the paper edit.

## Ducking

**Ducking** lowers music under speech. It is offered for an audio clip that is not linked to a video (an imported music file, or detached audio). Click **Duck under speech**: the music drops by 15 dB wherever the other enabled audio clips have transcribed words, with short fades before and after. After editing, **Update ducking** recomputes it; removing the card removes it. Mute ranges stay.

## Titles and lower thirds

In the toolbar below the flow:

- **Title** adds a 3 s title centred in the picture, at the cursor.
- **Lower third** adds a 5 s name-and-role caption near the bottom left, at the cursor.

Both are *text clips* on the lane above the pictures they cover. Like any clip, they can be moved, trimmed (as long as you want), split, disabled and faded; they take no speed, keyframes or crop.

Select the text clip and edit it in the **Clip** tab, under **TEXT**:

- the text (several lines allowed; saved when you leave the field, or with Ctrl + Enter);
- **Style**: Title (centred) or Lower third (switching resets the size and the box to that style's defaults);
- **Size**: small to extra large, relative to the picture;
- **Text colour**;
- **Box behind text**, with its colour and opacity. Without a box, the text has a soft shadow.

The preview, the MP4 render and the Camtasia export show the same text with the same font (Inter).

## In other editors

Fades, speed, mute ranges and titles are exported to Camtasia ([Camtasia export](../output/camtasia-export.md)); titles become Camtasia text callouts, with one box around all lines instead of one per line. OTIO and EDL keep fades on audio, speed and titles only as notes for other tools: speed is not applied, titles are empty gaps, and mute ranges are not exported. The export reports what it left out.

## Zoom and pan

Replaced by [keyframed transforms](keyframes.md): a zoom is a keyframe with a larger size between keyframes at the normal size.

## Technical notes

The effects list is in `frontend/src/effects.ts` (one entry and one card body per effect). Models, formulas, the render and the export mapping are in [transitions, effects and titles](../../architecture/effects-and-titles.md); tests are in the [validation record](../../validation/2026-11-11-finishing-features.md). The effects come from the backlog in [Camtasia findings](../../decisions/0003-camtasia-findings.md).
