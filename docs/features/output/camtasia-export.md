# Camtasia export

**Export → Camtasia project** writes `edit.tscproj` into the project's `exports` folder. Open it in Camtasia 2023.4 or later on Windows (the format opens in newer versions too). The Mac `.cmproj` format and a media-pack fallback are not supported.

The project keeps your original media where they are: Camtasia references them by path, so open it on the computer that has the files (or relink the media).

## What is exported

| In Video-Flow | In Camtasia |
|---------------|-------------|
| Each video lane | A track, in the same order; independent audio lanes follow |
| A video clip with its linked audio | One clip carrying both |
| Clip position, length and source range | The same, frame accurate |
| Picture position and size | The same |
| Rotation, opacity and keyframes ([keyframed transforms](../finishing/keyframes.md)) | The same (rotation could not be checked in Camtasia) |
| Image clips and freeze frames | Image clips |
| Clip volume, mute ranges and ducking | Volume and volume keyframes |
| Speed | The clip's speed |
| Fade in and out | A Camtasia fade on that edge |
| Dissolve | A Fade transition |
| Dip to black | A fade through black (a Fade if your template has none) |
| Dip to white | A Fade |
| Titles and lower thirds | Text callouts (one box around all lines, no shadow) |

## What is not exported

Crop, clip backgrounds, the sound crossfade of transitions, empty clips (Camtasia positions are absolute) and disabled clips. The export tells you what it left out and saves the list as `edit.report.json` next to the project.

## Looking exactly like your Camtasia

Camtasia project files are not documented, so Video-Flow builds the file from a template. By default it uses a built-in template that matches Camtasia 2023.4.3. To follow *your* Camtasia version and settings, save any project in Camtasia and put it in a `templates` folder next to the application as `camtasia.tscproj`: its structures are reused (your media and private details are not). If a needed structure is missing from your template, the built-in one is used and a warning says so.

From a terminal: `videoflow export BUNDLE --camtasia [--camtasia-template PATH]`.

## Good to know

Opening the result in Camtasia was checked structurally against a real Camtasia 2023.4.3 project; a hands-on check on Windows is still pending, notably the vertical direction of positions and rotation.

## Technical notes

The writer is `exporters/camtasia.py`. The precise mapping (ticks, parameters, template rules) is in [transitions, effects and titles](../../architecture/effects-and-titles.md#camtasia-writer); tests are in the [validation record](../../validation/2026-11-11-finishing-features.md#camtasia-export). This page covers EXP-06 of the [functional spec](../../product/functional-spec.md); other formats are in [render and export](render-and-export.md).
