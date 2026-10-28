# 06. Render and export

## 1. Render pipeline overview

```mermaid
flowchart LR
  P[project.json] --> C[Compile<br/>resolved timeline]
  C --> N[Normalise inputs<br/>canvas, fps, HDR, audio]
  N --> G[Build FFmpeg graph<br/>runs, transitions, overlays]
  G --> L1[Pass 1: audio-only<br/>loudnorm measure]
  L1 --> R[Pass 2: full render<br/>video + normalised audio]
  R --> V[Validate<br/>ffprobe, ebur128, duration]
  V --> O[renders/*.mp4 + log.json]
```

The **resolved timeline** is a flat, frame-quantised structure produced from `project.json` (same function that feeds the OTIO compiler): ordered main-line clips with extended source ranges (handles), transitions with absolute positions, overlays with absolute positions. Both OTIO export and FFmpeg render consume it, which guarantees they describe the same edit.

## 2. Input normalisation

Applied per input before any transition or concatenation (all `xfade` inputs must share resolution, frame rate, pixel format and timebase).

**Video**
1. Rotation: FFmpeg auto-rotation (default) honours display-matrix metadata.
2. HDR to SDR when the source is HLG/PQ and the output is SDR:
   `zscale=t=linear:npl=100,format=gbrpf32le,zscale=p=bt709,tonemap=tonemap=hable:desat=0,zscale=t=bt709:m=bt709:r=tv`
   (alternative: `libplacebo` when available, better quality, GPU).
3. Fit to canvas: `fit` = `scale=W:H:force_original_aspect_ratio=decrease,pad=W:H:(ow-iw)/2:(oh-ih)/2`; `fill` = `scale=...:increase,crop=W:H`. Default `fit` for main line, `fill` for B-roll.
4. `setsar=1,fps=<project rate>,format=yuv420p,settb=AVTB` (CFR conversion handles VFR phone footage).

**Audio**
- `aresample=48000:async=1,aformat=sample_fmts=fltp:channel_layouts=stereo,asetpts=PTS-STARTPTS`.
- Input without audio: generate silence with `anullsrc` for the clip duration.
- Mono lavalier on one channel: per-asset option to duplicate the left or right channel (`pan`).

**Seeking**: each clip is a separate input with `-ss <in> -t <duration>` placed before `-i`. Input seeking is frame-accurate when re-encoding and avoids decoding the whole file.

## 3. Cuts, transitions and the handle model

Video-Flow uses NLE semantics: a transition is **centered on the cut** by default and consumes **handles** (media beyond the visible in/out points). The total duration is therefore the same with or without transitions, and the render matches the exported OTIO/XML.

Definitions for main-line clips `0..n`:
- `v_i`: visible duration of clip `i` (cut to cut)
- `T_k`: duration of the transition between clip `k-1` and clip `k` (0 for a hard cut)
- Centered alignment: clip `k-1` is extended by `T_k/2` after its out point, clip `k` by `T_k/2` before its in point
- `r_i = v_i + left_handle_i + right_handle_i`: rendered duration of clip `i`

Graph construction:
1. Group consecutive clips separated by hard cuts into **runs**; each run is joined with the `concat` filter (video and audio together), with 10 ms audio micro-fades at each internal cut (`afade`) to avoid clicks.
2. Chain runs with `xfade` (video) and `acrossfade` (audio). For the transition `k`:

   `offset_k = Σ_{i<k} r_i − Σ_{j≤k} T_j`

   Final duration = `Σ r_i − Σ T_j = Σ v_i` (the hard-cut duration), within one frame.

Handle check (TR-06): if the source does not contain enough media for a handle, the UI proposes: shorten the transition, switch alignment to `start` (transition entirely after the cut, using only the right clip's head handle) or `end`, or accept a freeze-frame extension (`tpad=stop_mode=clone`), flagged in the render log.

### Example (3 clips, one 0.5 s dissolve, one hard cut)

Clip A: `rush1.mov` visible 10.00 to 18.00 → rendered 10.00 to 18.25 (right handle 0.25).
Clip B: `rush4.mov` visible 3.20 to 9.00 → rendered 2.95 to 9.00 (left handle 0.25).
Clip C: `rush2.mov` visible 0.00 to 5.00, hard cut after B.

```bash
ffmpeg -y \
  -ss 10.00 -t 8.25 -i rush1.mov \
  -ss 2.95  -t 6.05 -i rush4.mov \
  -ss 0.00  -t 5.00 -i rush2.mov \
  -/filter_complex graph.txt \
  -map "[vout]" -map "[aout]" \
  -c:v libx264 -preset slow -crf 18 -pix_fmt yuv420p -movflags +faststart \
  -c:a aac -b:a 192k -ar 48000 \
  -progress pipe:1 -nostats out.mp4
```

`graph.txt` (the graph is always written to a file: Windows command lines are length-limited; `-/filter_complex <file>` needs FFmpeg ≥ 7):

```text
[0:v]scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30,format=yuv420p,settb=AVTB[v0];
[1:v]scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30,format=yuv420p,settb=AVTB[v1];
[2:v]scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30,format=yuv420p,settb=AVTB[v2];
[0:a]aresample=48000:async=1,aformat=sample_fmts=fltp:channel_layouts=stereo,asetpts=PTS-STARTPTS[a0];
[1:a]aresample=48000:async=1,aformat=sample_fmts=fltp:channel_layouts=stereo,asetpts=PTS-STARTPTS,afade=t=out:st=6.04:d=0.01[a1];
[2:a]aresample=48000:async=1,aformat=sample_fmts=fltp:channel_layouts=stereo,asetpts=PTS-STARTPTS,afade=t=in:d=0.01[a2];
[v1][a1][v2][a2]concat=n=2:v=1:a=1[vrun1][arun1];
[v0][vrun1]xfade=transition=fade:duration=0.5:offset=7.75[vout];
[a0][arun1]acrossfade=d=0.5:c1=tri:c2=tri[aout]
```

Check: `offset = r_A − T = 8.25 − 0.5 = 7.75`; output duration = 8.25 + 6.05 + 5.00 − 0.5 = 18.80 = 8.00 + 5.80 + 5.00.

### Overlays (V2 B-roll, A2 music)
- V2 clip: normalised with `fill`, shifted with `setpts=PTS-STARTPTS+<t>/TB`, composited with `overlay=enable='between(t,<t>,<t+d>)':eof_action=pass`.
- A2 clip: `adelay` to its position, mixed with `amix=normalize=0` and per-item gain; optional ducking of music under speech with `sidechaincompress` (P2).
- V2 audio is muted by default (`mode: muted`).

### Titles and subtitles (P2)
`drawtext` for title cards and lower thirds (font file bundled), `subtitles` filter for burn-in from the generated SRT.

## 4. Transition catalog

Note the FFmpeg naming trap: `xfade=fade` is the classic cross dissolve, while `xfade=dissolve` is a random-pixel dissolve.

| Video-Flow id | Label | FFmpeg `xfade` | Audio default | OTIO | FCPXML | FCP7 XML | EDL | Camtasia | Prio |
|-------------|-------|----------------|---------------|------|--------|----------|-----|----------|------|
| `cut` | Cut | none (concat) | 10 ms micro-fade | none | none | none | C | none | P0 |
| `dissolve` | Cross dissolve | `fade` | `acrossfade` tri | `SMPTE_Dissolve` | Cross Dissolve | Cross Dissolve | D | template | P0 |
| `dip_black` | Fade through black | `fadeblack` | crossfade | Custom (+ metadata) | fallback dissolve (P2: native) | fallback dissolve | D | template | P0 |
| `dip_white` | Fade through white | `fadewhite` | crossfade | Custom | fallback dissolve | fallback dissolve | D | template | P0 |
| `wipe_{left,right,up,down}` | Wipe | `wipeleft`… | crossfade | Custom | fallback dissolve | fallback dissolve | D | template | P1 |
| `slide_{left,right,up,down}` | Slide | `slideleft`… | crossfade | Custom | fallback dissolve | fallback dissolve | D | template | P1 |
| `smooth_{left,right,up,down}` | Smooth push | `smoothleft`… | crossfade | Custom | fallback dissolve | fallback dissolve | D | fallback | P1 |
| `circle_open` / `circle_close` | Iris | `circleopen` / `circleclose` | crossfade | Custom | fallback dissolve | fallback dissolve | D | fallback | P1 |
| `radial` | Clock wipe | `radial` | crossfade | Custom | fallback dissolve | fallback dissolve | D | fallback | P1 |
| `zoom_in` | Zoom | `zoomin` | crossfade | Custom | fallback dissolve | fallback dissolve | D | fallback | P1 |
| `pixelize` | Pixelize | `pixelize` | crossfade | Custom | fallback dissolve | fallback dissolve | D | fallback | P1 |
| `noise_dissolve` | Noise dissolve | `dissolve` | crossfade | Custom | fallback dissolve | fallback dissolve | D | fallback | P2 |
| `custom_expr` | Custom expression | `custom` + `expr` | crossfade | Custom | fallback dissolve | fallback dissolve | D | fallback | P2 |

Rules:
- Every transition keeps its exact definition in OTIO metadata (`videoflow.transition`), so a Video-Flow round trip is lossless even when other tools only see a dissolve.
- The UI shows the fallback for the currently targeted export format (TR-08).
- Camtasia "template" means the transition object is cloned from a template project (see §8.3).
- GPU variants (`xfade_opencl`, `xfade_vulkan`) are an optimisation, not a requirement.

## 5. Render strategies

| Strategy | When | How |
|----------|------|-----|
| **A. Single graph** (MVP) | Up to ~40 main-line clips | One FFmpeg process, one graph, one input per clip. Simple and exact. |
| **B. Chunked + cached** (P1) | Long projects, frequent re-renders | Split the resolved timeline at hard cuts into chunks (runs plus transition regions). Render each chunk to a mezzanine (ProRes 422 LT or DNxHR SQ, PCM audio) keyed by the hash of its spec; chunks run in parallel; unchanged chunks are reused. Concatenate mezzanines with the concat demuxer (stream copy), then one final encode with loudness normalisation. |

Strategy B makes "change one take and re-render" take seconds instead of minutes.

## 6. Loudness and encoding

**Loudness**: pass 1 renders audio only (`-vn`, same graph) through `loudnorm=I=-14:TP=-1:LRA=11:print_format=json`; pass 2 applies the measured values (`measured_I`, `measured_TP`, `measured_LRA`, `measured_thresh`, `offset`, `linear=true`). Targets configurable per preset.

**Presets**

| Preset | Video | Audio | Container |
|--------|-------|-------|-----------|
| `draft` | 960x540, libx264 `ultrafast` CRF 28 | AAC 128k | MP4 |
| `youtube_1080p` | libx264 `slow` CRF 18, High profile, yuv420p; HW: `h264_videotoolbox` / `h264_nvenc` / `h264_qsv` / `h264_amf` at ~16 Mb/s | AAC 192k, 48 kHz | MP4 `+faststart` |
| `youtube_4k` | libx265 CRF 20 `-tag:v hvc1`; HW: `hevc_videotoolbox` / `hevc_nvenc` at ~45 Mb/s | AAC 256k | MP4 `+faststart` |
| `master` | ProRes 422 HQ (`prores_ks -profile:v 3`) | PCM 24-bit | MOV |
| `vertical_1080x1920` (P2) | as `youtube_1080p`, per-clip crop position | AAC 192k | MP4 |

Hardware encoders are detected at startup (`ffmpeg -encoders` plus a one-frame test encode) and used when the preset allows; software is the fallback.

## 7. Progress, cancellation, validation

- Progress: parse `-progress pipe:1` (`out_time_us`) against the expected duration; emitted as SSE events with ETA.
- Cancellation: send `q` on stdin, then terminate after a grace period; partial output deleted.
- Validation after render: ffprobe duration within one frame of the timeline, stream parameters match the preset, `ebur128` integrated loudness within ±1 LU of target, no unexpected black frames at cut points (`blackdetect` on a 0.2 s window around each cut).
- `renders/<name>.log.json`: FFmpeg version, full argument list, graph, timings, validation results, warnings (freeze-frame handles, HDR conversions).

## 8. Exports

### 8.1 Feature matrix

| Feature | OTIO / OTIOZ | FCPXML | FCP7 XML | CMX 3600 EDL | AAF (P2) | Camtasia |
|---------|--------------|--------|----------|--------------|----------|----------|
| Cuts and trims | yes | yes | yes | yes | yes | yes |
| Dissolves | yes | yes | yes | yes | yes | yes (template) |
| Other transitions | metadata + Custom | fallback dissolve | fallback dissolve | fallback dissolve | fallback dissolve | template subset |
| Multiple video tracks (B-roll) | yes | yes (connected clips) | yes | no (V1 only) | yes | yes |
| Audio tracks | yes | yes | yes | limited | yes | yes |
| Clip gain / fades | metadata only | to verify (P2 writer) | to verify | no | no | template |
| Markers | yes | yes | yes | as comments | no | yes |
| Alternates (EXP-07) | disabled ALT tracks | auditions | disabled ALT tracks | no | no | disabled tracks |
| Media bundled | OTIOZ | no | no | no | no | `.cmproj` (macOS) |

"To verify" items are checked during Phase 3 interop tests; the export dialog reports what was dropped or approximated.

### 8.2 Per-format notes

- **OTIO (P0)**: written by the core library from the compiled timeline (05 §6). `.otioz` bundles media for handoff to another machine. Primary targets: DaVinci Resolve, Premiere Pro (recent versions), Kdenlive (native OTIO since 25.04), Avid (preview).
- **FCPXML (P0)**: `fcpx_xml` adapter from `OpenTimelineIO-Plugins`, then a post-processor adds `<audition>` elements when alternates are included. The emitted FCPXML version is checked against the installed Final Cut Pro during interop tests.
- **FCP7 XML (P1)**: `fcp_xml` adapter. Broadest legacy compatibility (Premiere, Resolve, OpenShot).
- **CMX 3600 EDL (P0)**: `cmx_3600` adapter; main video track only, 32-character reel names derived from asset ids with a mapping table exported alongside; useful as a last resort.
- **AAF (P2)**: OTIO AAF adapter (pyaaf2); clips, gaps and transitions only.
- **SRT / VTT (P0)**: words inside the cut mapped from source time to timeline time; max 42 characters per line, 2 lines, minimum 1 s per cue, split on punctuation and pauses; fillers removed.
- **Paper edit (P0)**: Markdown and CSV, one row per main-line clip: order, beat label, asset file, source in/out (timecode), duration, transcript.

### 8.3 Camtasia writer (P1)

Implemented for Windows as described in [19](19-camtasia-export.md), which supersedes this section where they differ (no media pack or `.cmproj`).

Camtasia project files (`.tscproj`) are JSON, undocumented and versioned. Community libraries (`camtasio`, `tscprojpy`, `camtasia`) document the structure: canvas settings, a source bin of media, and a timeline of tracks with clips, effects and transitions. On macOS a project is a `.cmproj` directory containing `project.tscproj` and media. Camtasia does not appear to import EDL, XML or OTIO, so a native writer is the only route.

Strategy: **template-based generation**.
1. A template project is saved once with the user's Camtasia version (Windows or macOS): one video clip, one audio clip, one clip on a second track, one marker, and one instance of each supported transition. The app can also ship a default template per known Camtasia version.
2. The writer reads the template to learn the version-specific structure: time units and edit rate, source bin entry schema, media object types, transition objects, track attributes.
3. It generates the project by cloning these objects and filling paths, ranges and positions from the resolved timeline. Unsupported transitions fall back to the template's fade.
4. Validation: structural check with the library's validator, then a manual open-in-Camtasia smoke test per supported version.

Fallback when the writer is not compatible with the user's version: **media pack** export, i.e. one rendered file per main-line clip (numbered in order, with handles) plus SRT, ready to drag onto the Camtasia timeline.

### 8.4 Re-import (P2)
Read an `.otio` edited elsewhere; match clips back to Video-Flow items by `videoflow` metadata, or by asset path and overlapping source range; report unmatched clips. Allows "triage in Video-Flow, finish in Resolve, come back to swap a take".
