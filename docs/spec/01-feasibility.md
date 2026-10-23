# 01. Feasibility study

## 1. Verdict

**Feasible, with mature building blocks for every requirement.** No research breakthrough is needed. The real difficulty is not any single component but:

1. **Grouping quality** on footage where many clips carry little or no speech (hands opening a box, product close-ups).
2. **Scope control**: the request touches everything an NLE does. Trying to compete with Resolve or Premiere on editing depth would sink the project. Video-Flow must stay an assembly tool whose core value is *take triage*, with a clean handoff for finishing.
3. **Camtasia export**, which relies on an undocumented, versioned JSON format.

Recommendation: start with a one-week **analysis spike** on real rushes (CLI + notebook, no UI) to validate grouping accuracy before building the editor (see 07-roadmap.md, Phase 0).

## 2. Requirement-by-requirement assessment

| # | Requirement | Feasibility | Main building blocks | Main risk | Relative effort |
|---|-------------|-------------|----------------------|-----------|-----------------|
| R1 | Assemble, cut, trim | High | Custom canvas timeline (React), word-snapping from transcript | Frame-accurate preview in a browser | M |
| R2 | Visualise duplicates as branching timeline / flow | High | Beat/alternative data model, stacked "branch timeline", React Flow overview | UX density with many takes | M |
| R3 | Choose transitions | High | FFmpeg `xfade` (dozens of built-in transitions + custom expressions), `acrossfade` | Parity of transitions across export formats | S |
| R4 | Project file, standard format | High | OpenTimelineIO (OTIO) | Alternates have no native OTIO concept (solved via metadata + disabled tracks) | S |
| R5 | Render with FFmpeg | High | Generated `filter_complex` graphs, hardware encoders | Phone footage quirks: VFR, HDR (HLG), rotation | M |
| R6 | Export to other editors incl. Camtasia | Medium-High | OTIO adapters (FCPXML, FCP7 XML, EDL, AAF), custom Camtasia writer | Camtasia format undocumented and version-dependent | M (Camtasia: M/L) |
| R7 | Transcription with time codes | High | Whisper large-v3-turbo / Parakeet TDT 0.6B v3 with word timestamps | French accuracy of word timestamps (mitigated by forced alignment) | S |
| R8 | Group equivalent videos with a lightweight local LM | Medium-High | Multilingual text embeddings, visual embeddings, audio cross-correlation, clustering; tiny LLM for labels | A tiny LLM alone is not reliable for grouping (see §5) | M/L |
| R9 | Aligned comparison of similar takes | High | Word-level sequence alignment between takes, synchronised players | None significant | M |

S = days, M = 1 to 2 weeks, L = 3+ weeks (single developer, AI-assisted).

## 3. Is there a standard project format?

There is **no universal standard** that every editor reads and writes losslessly. The landscape:

| Format | Nature | Who reads it | Notes |
|--------|--------|--------------|-------|
| **OpenTimelineIO** (`.otio`, `.otioz` bundle with media) | Open, JSON, Academy Software Foundation project | DaVinci Resolve (since 18.5), Premiere Pro (25.6+ per third-party docs), Kdenlive (native since 25.04), Avid Media Composer (preview, Windows) | Closest thing to a vendor-neutral standard. Python + C++ libraries. Adapters to other formats ship separately in `OpenTimelineIO-Plugins` since v0.17. |
| FCPXML | Apple, XML | Final Cut Pro, Resolve, many tools | Has a native **audition** element (alternate clips), useful for our alternates. |
| FCP7 XML (xmeml) | Legacy XML | Premiere Pro, Resolve, OpenShot, many others | Old but the most widely imported XML. Adobe's historical recommendation for interchange. |
| CMX 3600 EDL | Text, SMPTE-era | Almost everything | One video track, cuts and dissolves/wipes only. Good lowest common denominator. |
| AAF | Binary, AMWA | Avid, Resolve, Premiere, Pro Tools | Heavy; OTIO adapter handles clips, gaps, transitions (no effects or markers). |
| Camtasia `.tscproj` | Proprietary JSON | Camtasia only | No public spec. Community Python libraries exist (`camtasio`, `tscprojpy`, `camtasia`). Camtasia does not appear to import EDL/XML/OTIO, so a native writer is required. |
| MLT XML / `.kdenlive` | Open XML | Kdenlive, Shotcut, `melt` | Not needed directly since Kdenlive now imports OTIO natively. |

**Decision:** OTIO is the canonical exchange format; the internal project file (`project.json`) holds what OTIO cannot express well (beats, alternatives, analysis links) and is compiled to OTIO deterministically. All other exports derive from the compiled OTIO, except Camtasia and FCPXML auditions which need dedicated writers.

## 4. Is FFmpeg sufficient for production rendering?

**Yes, for this scope.** FFmpeg covers:

- frame-accurate trimming (input seeking is accurate when re-encoding),
- concatenation of heterogeneous sources after normalisation (scale, pad, fps, pixel format, sample rate),
- transitions through `xfade` (fade, wipes, slides, circles, dissolve, pixelize, zoom, custom expressions) and `acrossfade` for audio,
- overlays (B-roll on a second track, logos, picture-in-picture), `drawtext` titles, subtitle burn-in,
- loudness normalisation (`loudnorm`, two-pass), ducking (`sidechaincompress`),
- HDR to SDR tone mapping (`zscale` + `tonemap`, or `libplacebo`), CFR conversion of variable frame rate phone footage,
- hardware encoding (VideoToolbox on macOS, NVENC, Quick Sync, AMF).

Limits that do not matter here: no real-time interactive preview engine, no motion graphics authoring, no colour grading UI. Preview is handled separately in the browser with proxies (see 03-architecture.md §6).

FFmpeg 8.0 also ships an optional `whisper` audio filter (whisper.cpp inside the filter graph). It is interesting but depends on a build with `--enable-whisper` and outputs segment-level text, so it is an optional engine, not the default.

Alternatives considered: MLT (`melt`, the Kdenlive/Shotcut engine) and GStreamer Editing Services. Both are capable but add a dependency without solving a problem FFmpeg cannot.

## 5. Can an ultra-light local LM group the takes?

Partially, and it should not be the primary mechanism.

- Sub-4B models (Gemma 4 E2B/E4B, Qwen3 small sizes, Phi-4-mini class) are good at **short structured tasks**: give a 3-to-6-word label to a beat, summarise it, flag a false start ("attends, je recommence"), flag off-topic chatter, pick a best take with a one-line reason. With JSON-schema-constrained decoding (Ollama `format`, llama.cpp grammars) the output is reliable enough.
- They are **not reliable** for global clustering over dozens of segments: context limits, ordering bias, and non-determinism make the grouping unstable between runs.

**Recommended design:** grouping is done by deterministic signal fusion (multilingual text embeddings + lexical alignment + visual embeddings + audio cross-correlation) followed by clustering with a user-adjustable threshold. The LLM runs per beat, after clustering, on small inputs. The pipeline must still work if the LLM is disabled (keyword-based labels as fallback).

## 6. The duplicate problem, made explicit

The request mentions several kinds of "same scene". They need different detectors and different editing affordances:

| Relation | Example | Detection signal | Editing affordance |
|----------|---------|------------------|--------------------|
| **RETAKE** | The same sentence said again later, maybe from another framing | Transcript similarity (lexical alignment + semantic embedding) | Alternatives of one beat; pick one; word-aligned comparison |
| **PARTIAL RETAKE / FALSE START** | Speaker stops after 4 words and restarts | Alignment covers only a prefix of the beat; LLM flag | Shown as a short alternative, auto-rejected by default |
| **SIMULTANEOUS** (same audio, different video) | Two cameras (or phone + camera) recording the same moment | Audio cross-correlation peak + overlapping recording times | **Sync group** (multicam): switch angles, keep the best audio source |
| **VISUAL DUPLICATE** (same visual, different audio) | Same close-up shot twice with different narration, or silent B-roll repeated | Visual embedding similarity per shot, low transcript similarity | Alternatives of a visual beat; option to take video from one take and audio from another (unlinked audio) |

"Same audio, different video" is ambiguous in the request: it is either a multicam recording (identical waveform, detected by cross-correlation) or a retake of the same words with another framing (similar text, different waveform). Both are handled.

## 7. Existing tools and the gap

| Tool | What it does | Gap relative to this request |
|------|--------------|------------------------------|
| AutoCut Repeat (Premiere / Resolve plugin) | Detects repeated sentences, keeps the best take | Works inside one sequence, cloud processing, no cross-file B-roll grouping, no Camtasia |
| FireCut (Premiere plugin) | Removes repeated phrases | Only consecutive repetitions within one clip |
| Cutback Selects / Premiere Assistant | Transcript-based rough cut, retake removal, handoff to Premiere / Resolve / FCP | Commercial, cloud-centric, speech-only grouping |
| Descript, Async, other AI editors | Transcript editing, retake removal | Proprietary project formats, limited interchange, no aligned take comparison |
| DaVinci Resolve Take Selector, FCP auditions | Manual alternate-take management | No automatic detection |

The gap Video-Flow fills: **cross-file grouping of speech and non-speech takes, an aligned comparison view, fully local processing, open project format, and Camtasia output.**

## 8. Hardware and performance envelope

Assumptions: 30 to 90 minutes of rushes, 1080p to 4K, mostly phone or mirrorless footage, French speech.

| Task | Apple Silicon (16 GB+) | Windows + NVIDIA GPU | CPU only |
|------|------------------------|----------------------|----------|
| Proxy generation (720p, short GOP) | Faster than real time (VideoToolbox) | Faster than real time (NVENC) | Around real time |
| ASR, word timestamps | Minutes for an hour of audio | Minutes | Tens of minutes (Parakeet is much faster than Whisper on CPU) |
| Visual embeddings (1 fps sampling) | Minutes | Minutes | 5 to 15 minutes per hour |
| Clustering, alignment | Seconds | Seconds | Seconds |
| Tiny LLM labelling (per beat) | Seconds per beat | Seconds per beat | Several seconds per beat |

Order-of-magnitude figures, to be measured in Phase 0. Target: full analysis of one hour of rushes in under 15 minutes on a recent laptop with acceleration.

## 9. Key risks (details in 07-roadmap.md)

1. Grouping accuracy on non-speech footage.
2. Browser preview fidelity: frame accuracy, HEVC/HDR playback differences across browsers (mitigated by proxies).
3. Phone footage normalisation (VFR, HLG HDR, rotation metadata, mixed frame rates).
4. Camtasia format changes between versions.
5. Transition semantics differing between NLEs (handles vs overlap).
6. Scope creep towards a full NLE.

## 10. Effort estimate (rough order of magnitude)

| Phase | Content | Estimate |
|-------|---------|----------|
| 0. Spike | Analysis pipeline CLI, grouping metrics on real rushes | 1 week |
| 1. MVP | Ingest, analysis, branch timeline, compare view, basic trims, dissolve/fade transitions, FFmpeg render, OTIO + FCPXML + EDL + SRT export | 6 to 8 weeks |
| 2. Pro features | Sync groups (multicam), unlinked audio, transcript editing, full transition catalog, flow overview | 3 to 4 weeks |
| 3. Interop and packaging | Camtasia writer, AAF, FCPXML auditions, desktop packaging | 2 to 4 weeks |

Single developer, AI-assisted coding. To be refined after Phase 0.

## 11. References

- OpenTimelineIO adapters documentation: https://opentimelineio.readthedocs.io/en/v0.15/tutorials/adapters.html
- OpenTimelineIO releases (adapters moved to `OpenTimelineIO-Plugins`): https://github.com/AcademySoftwareFoundation/OpenTimelineIO/releases
- Kdenlive native OTIO support (adapter deprecated): https://pypi.org/project/otio-kdenlive-adapter
- OTIO import in Premiere 25.6+ and Resolve (Remotion docs): https://www.remotion.dev/docs/export-opentimeline
- Camtasia project libraries: https://pypi.org/project/camtasio/ , https://pypi.org/project/tscprojpy/
- FFmpeg 8.0 whisper filter: https://www.heise.de/en/news/FFmpeg-8-0-integrates-Whisper-Local-audio-transcription-without-the-cloud-10522091.html
- Local ASR comparisons: https://openwhispr.com/blog/parakeet-vs-whisper-vs-nemotron , https://wz-it.com/en/blog/local-speech-to-text-gdpr/
- Retake removal tools: https://www.autocut.com/en/autocutrepeat , https://learn.firecut.ai/features/remove-repetition , https://cutback.video/guide/remove-retakes
