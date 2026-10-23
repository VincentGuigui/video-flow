# 07. Roadmap, risks and open questions

## 1. Phases

### Phase 0: analysis spike (1 week)
Goal: prove that grouping works on real footage before any UI work.

Deliverables:
- `videoflow analyse <folder>` CLI: probe, audio extract, VAD, ASR (two engines compared: Whisper large-v3-turbo and Parakeet TDT 0.6B v3), segmentation, text and visual embeddings, relations, clustering, LLM labels.
- Static HTML or Markdown report: beats with thumbnails, takes, scores, flags.
- Hand-labelled ground truth for 2 to 3 real unboxing projects and the metrics of 04 §11.

Exit criteria:
- Pairwise F1 ≥ 0.85 on speech segments, ≥ 0.70 on visual segments (or a clear plan to reach it).
- Default ASR engine chosen for French; timings measured on the target machine(s).
- Go / no-go on the visual grouping approach (DINOv2 vs alternatives).

### Phase 1: MVP (6 to 8 weeks)

| Step | Content |
|------|---------|
| 1a Foundation | Project bundle, `project.json` schema v1 + migrations scaffold, job runner, SSE, media service (probe, proxies, sprites, peaks), pipeline integrated with caching |
| 1b Triage UI | Media bin, branch timeline (Branch / Cut modes), compare view with synchronised playback and divergence highlighting, inspector with score breakdown, sensitivity slider, beat corrections (move, merge, split, orphans) |
| 1c Editing | Trims with word and shot snapping, blade, ripple delete, auto-tighten, clip gain and fades, undo/redo, cut/dissolve/dip-to-black/dip-to-white transitions with handle checks, live preview |
| 1d Output | Render strategy A, presets, two-pass loudness, HDR tone mapping, validation; exports OTIO, OTIOZ, FCPXML, EDL, SRT/VTT, paper edit |

Exit criteria: the acceptance scenarios of 02 §8 pass on a real project; a 40-rush project goes from import to rendered MP4 with less than 30 minutes of user time (analysis excluded).

### Phase 2: pro features (3 to 4 weeks)
- Sync groups (multicam) with angle switching and audio source choice.
- Unlinked audio: replace a take's audio with another take's audio, auto-aligned.
- Transcript-driven editing; comping (ranges from several takes in one beat).
- Full transition catalog with preview renders; flow overview (React Flow).
- Render strategy B (chunked, cached, parallel).
- LLM global order suggestion; markers.
- **Script-guided grouping** (optional input): if an outline or script is provided, beats are seeded from it and takes are matched to script lines, which removes most grouping ambiguity.

### Phase 3: interoperability and packaging (2 to 4 weeks)
- Camtasia writer (template-based) + media pack fallback.
- FCP7 XML, FCPXML auditions, AAF.
- OTIO re-import (round trip).
- Interop test matrix: Resolve, Premiere, Final Cut Pro, Kdenlive, Camtasia (Windows and macOS).
- French UI; optional desktop packaging (Tauri shell with the Python backend as sidecar).

### Later ideas
- Natural-language shot search and automatic B-roll suggestions (match transcript nouns to visual-text embeddings).
- Vertical reframing (9:16) with subject tracking.
- YouTube chapters from beat labels; thumbnail frame suggestions.
- Music track with beat-synced cut suggestions and automatic ducking.

## 2. Risk register

| ID | Risk | Likelihood | Impact | Mitigation |
|----|------|-----------|--------|------------|
| K-01 | Grouping inaccurate on non-speech footage (B-roll) | Medium | High | Phase 0 benchmark; DINOv2 near-duplicate features; sensitivity slider; fast manual correction (drag, merge, split) with persisted constraints |
| K-02 | ASR drops fillers; word timestamps drift in French | Medium | Medium | Verbatim prompting, voiced-gap detection from VAD, forced alignment (WhisperX), Parakeet as alternative engine |
| K-03 | Browser cannot decode some sources (HEVC, HDR, 10-bit) | High | Medium | Always preview through H.264 8-bit SDR proxies |
| K-04 | Preview not frame-accurate | Medium | Low | FFmpeg render is the reference; preview renders for transitions; frame checks in validation |
| K-05 | Phone footage quirks (VFR, HLG, rotation, mixed frame rates) | High | Medium | Normalisation chain (06 §2); test corpus with real iPhone and Android files |
| K-06 | Camtasia format changes between versions | Medium | Medium | Template-based writer per version; media pack fallback |
| K-07 | OTIO adapter gaps (FCPXML version, gain, auditions) | Medium | Medium | Golden-file tests; post-processors; export report of dropped features |
| K-08 | Tiny LLM produces invalid or poor output | Medium | Low | Constrained decoding, validation and retry, keyword fallback, LLM optional |
| K-09 | Scope creep towards a full NLE | High | High | Non-goals in 02 §1; OTIO handoff for finishing; scope review at each phase gate |
| K-10 | Slow analysis on CPU-only machines | Medium | Medium | Engine auto-selection, smaller models, progressive UI (triage starts before visual features finish) |
| K-11 | Large single FFmpeg graphs (memory, time) | Medium | Medium | Render strategy B |
| K-12 | Model licences (attribution, usage terms) | Low | Low | Licence review per model; attributions in the About screen |

## 3. Open questions

| # | Question | Why it matters |
|---|----------|----------------|
| Q1 | Main machine: Mac Apple Silicon, Windows with NVIDIA GPU, or both? | Default engines (MLX / whisper.cpp vs CUDA), hardware encoders, Camtasia variant |
| Q2 | Cameras and audio: iPhone (HEVC, HLG HDR, VFR)? mirrorless? separate recorder or wireless lav? | Normalisation priorities, sync groups in MVP or not |
| Q3 | Spoken language: French only, or mixed French / English? | ASR configuration, filler lexicon, LLM prompt language |
| Q4 | Output formats: YouTube 16:9 only, or also 9:16 Shorts / Reels? | Whether vertical reframing moves up the roadmap |
| Q5 | Is Camtasia the usual finishing tool? Which version and OS? | If yes, the Camtasia export becomes the main deliverable and moves to Phase 1 |
| Q6 | Other editors to support first (Resolve, Premiere, Final Cut Pro)? | Order of interop tests and export polishing |
| Q7 | Typical volume per project (number of rushes, total duration)? | Render strategy and performance targets |
| Q8 | Is there usually a script or outline before shooting? | Script-guided grouping could replace much of the heuristic clustering |
| Q9 | Personal tool, internal tool, or open source? | Licensing choices for models and dependencies, packaging effort |
