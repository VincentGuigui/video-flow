# Audio tracks of video clips

A video imported with sound gives two clips: the picture, and its audio just below it, linked together. This page covers what you can do with the sound. For moving and trimming the pair, see [timeline and clip flow](unified-timeline.md).

## Silencing a clip

There is no mute button: use the **box on the clip** (its enable checkbox). A disabled audio clip stays visible in its lane and plays as silence. To silence only part of a clip, use [mute ranges](../finishing/clip-effects.md#mute-ranges).

## Detaching the audio

Click the **chain button** between the picture and its audio, or **Detach audio & video** in the Clip tab. Nothing moves, but from then on the audio clip moves, splits and trims on its own. This is how you slide a voice-over under another picture, or keep the sound of a clip while replacing its picture.

## Restoring the original audio

Select a video clip and click **Restore original audio** in the Clip tab. It is offered when the clip's file has sound and the clip is not already linked to that same sound. It:

1. adds a new audio clip from the video's file, with the same start and range as the picture, at full volume;
2. links it to the video (any audio the video was linked to is unlinked and stays where it is);
3. leaves every other audio clip alone, including the detached original: disable or delete it yourself;
4. moves the pair to the first free lane if the new audio would overlap another audio clip.

It is one undo step.

## Linking an audio clip to a picture

To link two separate clips (for example a recorder's track and a video), see [linking separate clips](unified-timeline.md#linking-separate-clips).

## Technical notes

Rules and code: [editor behaviour](../../architecture/editor-behaviour.md#audio-tracks). Tests: [validation record](../../validation/2026-11-12-manual-pages.md#audio-tracks).
