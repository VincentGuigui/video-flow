# FFmpeg setup

Video-Flow needs **FFmpeg 6.1 or newer** to read your media, make previews and thumbnails, and render. FFmpeg is a separate program, not included in Video-Flow: if you have none, Video-Flow offers to download it for you.

## At first start

When no usable FFmpeg is found, the **FFmpeg** window opens at start (before the AI models window). It tells you why FFmpeg is needed and what it would download: the version, who builds it, its licence (GPL-3.0), the size, the source address and the folder it goes into (`tools/ffmpeg` next to the application).

**Nothing is downloaded until you click Download and install.** A progress bar and **Cancel** are shown during the download; if it fails (network, disk, or a file that does not match its expected checksum) the window says why and nothing is installed. **Later** closes the window. Once installed, the app uses FFmpeg at once, with no restart.

On a system where no build is offered (Windows or Linux on ARM), the window explains how to install FFmpeg yourself.

**Settings → FFmpeg** opens the same window at any time, for example to see which version is used.

## Where Video-Flow looks

In this order: the paths set in settings, the `tools/ffmpeg` folder next to the application, then your `PATH`. A version older than 6.1 counts as missing.

## With the install scripts

When you install from the source code, the install scripts keep an FFmpeg 6.1+ that is already there. Otherwise they show the same information and **ask before downloading**. Add `--yes` (`-Yes` in PowerShell) to accept without asking, or `--no-ffmpeg` (`-NoFfmpeg`) to skip the check. Without a terminal and without `--yes`, nothing is downloaded and the script tells you what to do.

## Good to know

- The downloaded FFmpeg is installed unchanged, with its licence files. Its builder, not Video-Flow, provides its source code.
- Every download is checked against a known checksum before being installed.

## Technical notes

Lookup, the capability cache, pinned builds, API and scripts: [projects, cache and FFmpeg](../../architecture/projects-and-setup.md#ffmpeg). Tests: [validation record](../../validation/2026-11-12-manual-pages.md#ffmpeg-setup).
