# 08. Architecture review and revised implementation plan

Later accepted revisions: [09](09-interactive-editor.md) updates editing behavior; [10](10-desktop-shell.md) selects PySide6 + Qt WebEngine and native reference-in-place imports. Revision 10 supersedes this document's browser-first and pywebview/Tauri packaging decisions; the historical review and measurements below are retained for context.

Inputs: four evaluation reports (stack, analysis, render, model) on spec draft v0.1 (`docs/spec/00..07`), with experiments under `scratchpad/eval/{stack,analysis,render,otio}`. Container used for the tests: FFmpeg 6.1.1 (flite, loudnorm, xfade, zscale and tonemap are present), Python 3.13.17, Node 22.22, 4 CPUs, no GPU.

---

## 0. Revision after user answers (2026-10-23)

Targets: **Windows 11 (x64, ARM64 for Snapdragon) and Linux (x86_64)**. macOS is dropped: no MLX, no VideoToolbox, no `.cmproj`.

### 0.1 Acceleration policy: NPU → GPU → CPU

| Workload | 1st: NPU | 2nd: GPU | 3rd: CPU |
|---|---|---|---|
| AI inference (VAD, ASR, text and visual embeddings) | Intel Core Ultra: OpenVINO (NPU device) or ONNX Runtime OpenVINO EP. AMD Ryzen AI: ONNX Runtime VitisAI EP (Ryzen AI SDK, Windows). Qualcomm Snapdragon X: ONNX Runtime QNN EP (Windows ARM64). | ONNX Runtime CUDA EP (NVIDIA), DirectML EP (any GPU, Windows), OpenVINO GPU (Intel iGPU/Arc, Linux + Windows), ROCm/MIGraphX (AMD, Linux, best effort) | ONNX Runtime CPU EP (int8 models) |
| Local LLM labels (P1) | OpenVINO GenAI (Intel NPU), Ryzen AI / Lemonade (AMD), QNN GenAI (Qualcomm) | llama.cpp / Ollama with CUDA, Vulkan | llama.cpp / Ollama CPU |
| Video decode | — | NVDEC (`-hwaccel cuda`), QSV / VAAPI (Intel), D3D11VA / VAAPI (AMD), D3D11VA (any, Windows) | software decode |
| Video encode | — | `h264/hevc_nvenc`, `h264/hevc_qsv` or `_vaapi`, `h264/hevc_amf` or `_vaapi`, `h264_mf` (Windows) | libx264 / libx265 |

Consequences:
- **Engines are ONNX-first.** Every AI engine is an ONNX (or OpenVINO IR) model run through one `InferenceSession` factory in `videoflow/hw/ai.py` that probes the available providers, orders them NPU → GPU → CPU, verifies each with a one-shot warm-up (operator support on NPUs is partial), and falls back per model. User override in settings (`ai.device = auto | npu | gpu | cpu`). Selected device reported by `videoflow doctor` and in the UI.
- Models with dynamic shapes or unsupported operators on an NPU (e.g. Parakeet decoder loop) are split: encoder on NPU/GPU, decoder on CPU. Static-shape exports are preferred for NPUs. This is a Phase 0 measurement item.
- faster-whisper (CTranslate2) stays as the CPU/CUDA alternative ASR engine only; it has no NPU path.
- `videoflow/hw/video.py` probes `ffmpeg -hwaccels`, `-encoders`, and runs a one-frame test encode/decode per candidate; the render and proxy builders pick the first working one, libx264 otherwise. RND-02 stays P0.
- Python extras: `[openvino]` (openvino, onnxruntime-openvino), `[directml]` (onnxruntime-directml, Windows), `[cuda]` (onnxruntime-gpu), `[qnn]` (onnxruntime-qnn, Windows ARM64). AMD VitisAI EP ships with the Ryzen AI SDK (not on PyPI); the install script detects and documents it. Only one onnxruntime flavour may be installed per environment: the install script picks it from detected hardware.

### 0.2 Hypotheses added (not verifiable in this container, Phase 0 on target hardware)

| # | Hypothesis |
|---|---|
| H21 | Silero VAD, Parakeet TDT v3 encoder, MiniLM-L12 and DINOv2-small run on Intel NPU via OpenVINO with static shapes and are faster or more power-efficient than iGPU. |
| H22 | The same models run on AMD NPU (VitisAI EP, int8 quantised) and Qualcomm NPU (QNN EP, QDQ int8). |
| H23 | Python 3.13 wheels exist for onnxruntime-qnn (win_arm64) and the Ryzen AI SDK runtime; otherwise those targets pin Python 3.12 in their install profile. |
| H24 | FFmpeg static builds for win_arm64 provide `h264_mf` / D3D11VA usable on Snapdragon. |
| H25 | VAAPI encode on Linux works for Intel and AMD with the bundled FFmpeg build (driver-dependent). |

### 0.3 Installation and run scripts

- `scripts/install.sh` (Linux) and `scripts/install.ps1` (Windows): check/install uv, Python 3.13 via uv, Node 22 + pnpm (frontend build only), FFmpeg ≥ 6.1 (system package or pinned static build into `tools/ffmpeg/`), detect NPU/GPU and install the matching onnxruntime/OpenVINO extra, optionally pre-download models.
- `scripts/run.sh` / `scripts/run.ps1`: start `videoflow serve` and open the browser; pass-through for CLI commands.
- `docs/dependencies.md`: every runtime and dev dependency with version, licence, purpose, and per-accelerator matrix. Kept up to date by every WP that adds a dependency.

### 0.4 Plan changes

- WP1 also delivers the install/run scripts and `docs/dependencies.md`.
- WP3 also delivers `hw/video.py` (hwaccel/encoder probing with test encode).
- New **WP3b** `hw/ai.py`: provider probing, NPU → GPU → CPU ordering, warm-up validation, per-model fallback, settings override, `doctor` output. Tests here: CPU-only path, plus mocked provider lists for ordering and fallback.
- WP11 engines use the `hw/ai.py` session factory exclusively.

---

## 1. Decisions confirmed or changed

| Topic | Spec said | Verdict | Rationale | Evidence |
|---|---|---|---|---|
| D-1 Local web app | Browser SPA served by a local backend; Tauri sidecar in Phase 3 | **Keep, amend** | A browser cannot give the backend an absolute folder path. Add `GET /fs/list` (limited to allowed roots) and a typed-path fallback. Phase 3 shell: pywebview, with Tauri only if pywebview fails. Most packaging effort is freezing Python and the models. | stack/D-1: `webkitdirectory` uploads files and exposes no path; pywebview 6.2.1 has native dialogs |
| D-2 Python | 3.12 | **Change → 3.13** (`>=3.13,<3.14`) | cp313 wheels exist on win_amd64 and linux x86_64 for OTIO 0.18.1, ctranslate2, torch, onnxruntime, numpy (win_arm64 for Snapdragon to be verified, see §0). 3.14 is blocked by OTIO and whisperx. Security support runs to Oct 2029. Fall back to 3.12 only if a Phase 0 engine fails to install. | stack/D-2, render/(6): `uv` env on 3.13 installed the full set in 21 s. The model report preferred 3.12 but did not check wheels; stack and render did. |
| D-2 SSE library | sse-starlette implied | **Change → `fastapi.sse`** | Built into FastAPI 0.162. OpenAPI 3.1 gets an `itemSchema`. Pin the FastAPI minor version. | stack: probe app emitted text/event-stream |
| D-3 Frontend stack | React 19 + Vite + TanStack Query + Zustand + shadcn | **Keep, pin** | React 19.3, Vite 8 (Node ≥22.12), TanStack Query 5, Zustand 5 + Immer 11, Tailwind 4, shadcn CLI 4/Radix. No router. The project document lives in Zustand only. TanStack Query holds assets, jobs, transcripts, peaks and alignment. | stack/D-3 |
| Type generation | openapi-typescript | **Keep, pin TS ~6.0** | openapi-typescript 7.13 crashes on TypeScript 7.0.2 and works on 6.0.3. Add openapi-fetch and openapi-react-query. Export the SSE event union to `components/schemas`. | stack: `createKeywordTypeNode` TypeError |
| D-4 Custom canvas timeline | Canvas 2D; PixiJS if needed | **Keep** | Install React Flow only in Phase 2. | stack/D-4 |
| D-5 FFmpeg as subprocess | CLI subprocess, FFmpeg ≥7.0 | **Keep; change version policy** | Support ≥6.1 and recommend 7.x/8.x. Probe the capabilities instead of parsing the version string. Use `-/filter_complex` if the probe accepts it, otherwise `-filter_complex_script`. Ship a pinned static build to users. | render/(2): 6.1.1 rejects `-/filter_complex` (exit 8); `-filter_complex_script` works. stack: `-progress pipe:1` works and terminate gives rc 255. |
| D-6 OTIO interchange | OTIO with stock adapters, `project.json` as source of truth | **Keep; adapters changed** | `fcpx_xml` is not in OTIO-Plugins: it needs `otio-fcpx-xml-adapter`, and that adapter drops dissolves and writes FCPXML 1.8. FCPXML needs a custom writer, P1. AAF fails, so it is unsupported. EDL reel names are limited to 8 characters. OTIOZ needs real files. | render/(5a,5b) |
| D-7 Job system | Persistent SQLite job table plus ProcessPoolExecutor | **Change** | Use an in-memory asyncio job registry. The content-hash stage cache provides NFR-04: resuming means rerunning, and cached stages are skipped. FFmpeg runs as an asyncio subprocess. ML runs in long-lived `multiprocessing.Process` workers per engine class, and cancelling kills and respawns the worker. | stack/D-7: cancelling a ProcessPoolExecutor future does not stop the running task; spawn mode needs a `__main__` guard |
| Analysis store | `analysis.sqlite` (jobs, transcripts, …) | **Change** | Each stage writes JSON plus `.npy` under `features/` and `analysis/`, written atomically and keyed by hash. SQLite only for an optional index, kept outside cloud-synced folders. | stack/D-7: WAL on iCloud/Dropbox can corrupt the database |
| SSE vs WebSocket | SSE | **Keep** | One stream per tab, with `id` and `Last-Event-ID`. In Phase 1b, test 4 or more `<video>` elements plus SSE against the HTTP/1.1 limit of 6 connections per host. | stack/SSE |
| Auth | Token in the launch URL | **Change** | `?token=` sets an HttpOnly SameSite=Strict cookie, then redirects to drop the token. Every route checks the cookie and the Host header (`127.0.0.1:<port>`). EventSource and `<video>` cannot send an auth header. | stack/security |
| Undo owner | Zustand patches, `project/` command log and `history.jsonl`, all at once | **Change → one model** | Use semantic commands addressed by id (`PromoteTake`, `TrimItem`, …), sent in a PATCH batch with `base_revision`. The server returns the inverse; undo applies that inverse as a new revision. The client owns the undo stack. Drags are grouped into gesture transactions. `history.jsonl` is an append-only WAL and audit log, not the undo engine. Undo within a session is P0; undo across sessions is P1. | model/undo, stack/undo |
| Time representation | float seconds | **Change** | Store source times as integer microseconds and rates as rationals. The resolved timeline uses integer frames: each clip is `round(out·fps) − round(in·fps)` frames, and positions are cumulative sums. | model/time; render/(1a): float `-t` gives a 1–2 frame overshoot |
| Entity IDs | `seg_<asset>_<ms>_<ms>_<kind>`, counters in examples | **Change** | Opaque short ULIDs for every entity. Segments map to their bounds in a table. Re-segmentation goes through an IoU remap (≥0.5); anything left unmatched is marked "needs relink". | model/ID stability |
| Transitions / overlays keyed to item ids | `Transition{left,right}`, `anchor{itemId}` | **Change** | `Transition.afterItemId`. A transition becomes dormant, not deleted, when its items are no longer adjacent. Overlays anchor to `beatId` plus an offset from the visible start, or `{type:'project', time}`. | model/derived main line, overlays |
| Derived scores in `project.json` | `score`, `flags`, `alignOffset` stored | **Change** | Move them to the analysis cache and join them when read. `project.json` holds only decisions. | model/promote |
| Sync groups | `Asset.syncGroupId` with no entity behind it | **Change (schema only)** | Freeze `syncGroups[]`, `probe.video?`, `audioStreams[]` and `angleAssetId` in schema v1. The UI comes in Phase 2. | model/sync |
| D-8 Engines behind Protocols | Many engines with auto-selection | **Keep, YAGNI** | One implementation per Protocol, plus a second ASR engine for Phase 0. Extras per accelerator, see §0 (`[openvino]`, `[directml]`, `[cuda]`, `[qnn]`; VitisAI via AMD Ryzen AI SDK). Torch is not in the core install. | stack/D-8, analysis/env (torch with CUDA adds 4.4 GB) |
| Default ASR (CPU/Windows) | Whisper family | **Change → Parakeet TDT v3 ONNX int8** | RTF 0.11 against 0.55 for large-v3-turbo on 4 CPUs. Licence is CC-BY-4.0 (credit shown in About). | analysis/ASR speed |
| Default text embedding | EmbeddingGemma among the options | **Change** | EmbeddingGemma is gated (manual approval), so automatic download fails. Default to multilingual-e5-small or MiniLM, with thresholds set per model. | analysis/HF, thresholds Superseded by 18: MiniLM-L12 is the only text embedder. |
| VISUAL_DUPLICATE edges | Allowed between speech segments | **Change** | VISUAL_DUPLICATE is a clustering edge only between non-speech segments. For speech segments, visual similarity is kept as a "same setup" attribute. | analysis/VISUAL_DUPLICATE |
| Clustering | Agglomerative clustering with cannot-link handled as a large distance | **Change** | Use our own constrained average linkage that never merges across a cannot-link (n < 2000). | analysis/clustering: sklearn merged 2 beats at τ=0.7 |
| GCC-PHAT acceptance | Normalised peak ≥ 0.3 on an "8 kHz onset envelope" | **Change** | Use a 100 Hz onset envelope and accept on peak-to-sidelobe ratio ≥ 4 (sidelobes taken outside ±0.5 s). Refine on raw audio within ±50 ms. Store offset and drift. | analysis/GCC-PHAT: peak 0.479 for unrelated vs 0.491 for matching; PSR 9.34 vs 1.05 |
| D-9 Local-only by default | — | **Keep** | — | — |
| Repo layout | Root `videoflow/` | **Keep, amend** | Repo is `video-flow`, package and CLI are `videoflow`. Add a root `justfile`, `frontend/src/api/schema.gen.ts` (committed and checked in CI), `scripts/gen_samples.py`, and git-ignore `samples/`. Vite proxies `/api` to the backend. | stack/layout |

---

## 2. Hypotheses

### 2.1 Verified empirically, in this container

| # | Hypothesis | Result |
|---|---|---|
| H1 | The stack installs on Python 3.13 with uv | ✅ fastapi, pydantic, OTIO and its adapters, faster-whisper, onnx-asr and silero install in 21 s and import |
| H2 | The FFmpeg subprocess reports progress and can be cancelled | ✅ `-progress pipe:1` streams; `terminate()` gives rc 255 |
| H3 | The handle/xfade/acrossfade/concat graph in 06 §3 renders mixed inputs (720p25, 480p29.97 mono, vertical 24p with no audio) | ✅ Renders, but ❌ "within 1 frame" fails with float `-t`. ✅ Exact with `trim=end_frame` / `atrim=end_sample`: 565 frames = Σ − T. |
| H4 | acrossfade shortens audio by T, the same as xfade does for video | ✅ Sample-exact (18.80 s). `concat` pads each audio segment to its video length. |
| H5 | All xfade names in the catalog exist | ✅ On 6.1.1 (58 transitions, `custom` works) |
| H6 | The two-pass loudnorm JSON can be parsed | ✅ Result −14.0 LUFS, confirmed by ebur128. ❌ Digital silence gives `-inf`, so it needs a silent-input branch. |
| H7 | OTIO exports to OTIO, EDL, FCP7 XML, FCPXML and AAF | ✅ otio, otioz (with real files), fcp_xml. ⚠ EDL has a spurious event and truncated reels. ❌ FCPXML drops the dissolve. ❌ AAF fails. |
| H8 | `videoflow` metadata survives an OTIO round trip | ✅ |
| H9 | Parakeet is much faster than Whisper on CPU | ✅ RTF 0.11 vs 0.35 (small) and 0.55 (turbo) |
| H10 | Silero VAD runs without torch | ✅ ONNX, 0.4 s for 31 s of audio |
| H11 | PySceneDetect finds the cuts | ✅ 3 of 3 cuts on synthetic media, 0.6 s |
| H12 | DINOv2 separates near-duplicates | ✅ 0.99 for the near-duplicate vs 0.20–0.42 for other shots (synthetic). 14 frames/s on CPU. |
| H13 | Segmentation in 04 S9 handles real retake gaps | ❌ With 1 s gaps: 2 blocks out of 5 utterances, and the retake is missed |
| H14 | The PARTIAL_RETAKE suffix rule identifies false starts | ❌ It mislabels contained matches and misses the real false start |
| H15 | A cosine pre-filter at 0.45 separates unrelated text | ❌ e5: unrelated pairs score 0.77–0.83. MiniLM: 0.02–0.34. Thresholds must be set per model. |
| H16 | sklearn agglomerative clustering respects cannot-link | ❌ |
| H17 | GCC-PHAT normalised peak separates matching from unrelated audio | ❌ The peak does not; PSR does (9.34 vs 1.05) |
| H18 | openapi-typescript works with the current TypeScript | ❌ Fails with TS 7.0.2; ✅ works with TS 6.0.3 |
| H19 | ProcessPoolExecutor can cancel running ML tasks | ❌ |
| H20 | `-/filter_complex` works on the container's FFmpeg | ❌ It needs ≥7; `-filter_complex_script` works on 6.1 |

### 2.2 Deferred to Phase 0 on real rushes (target Windows and Linux)

1. French ASR: Parakeet ONNX vs turbo. Measure word error rate, whether fillers are kept, word-boundary error against hand-marked cuts, and timing on the target machines. Decide whether S5 (WhisperX) can be dropped.
2. Segmentation: the utterance as the unit, gap parameters (0.8/0.4/2.0 s), and the French restart-cue lexicon.
3. Text similarity calibration per embedding model (distribution of retake pairs vs unrelated pairs), giving θ_text and τ.
4. Contained-match vs prefix false-start logic (Smith-Waterman / rapidfuzz).
5. Visual similarity on real B-roll: DINOv2 vs pHash/histogram, and the sampling rate on CPU.
6. GCC-PHAT PSR threshold and drift on real phone plus camera pairs.
7. Quality weights against picks made by hand (target 60% agreement). Consensus built from complete takes only.
8. LLM label and flag precision vs the TF-IDF fallback (Ollama: gemma4 / qwen3 with thinking off).
9. PySceneDetect on handheld footage (pans, auto-exposure).
10. End-to-end timing budget (04 §12).
11. Interop: OTIO in Resolve and Premiere, the EDL, and the custom FCPXML in FCP and Resolve.
12. Windows: the asyncio Proactor loop under uvicorn, and spawned workers.
13. Compare view: 4 or more players plus SSE under the connection limit.

---

## 3. Spec corrections needed

| File | Section | Change |
|---|---|---|
| README | Title, key decisions | Product name is **Video-Flow** (rename everything left over from "takeflow"). Python 3.13. FFmpeg ≥6.1 supported, 7.x/8.x recommended and bundled. |
| 01 | §4, §8 | FFmpeg version policy. Measured CPU ASR speeds. The target of <5 min ASR per hour of audio needs acceleration. |
| 02 | PRJ-02 | Undo within a session is P0; undo across sessions is P1. |
| 02 | TL-01, 05/06 | A2 music track is P1 everywhere. The MVP has only V2 overlays. |
| 02 | TL-03 | Lift (leaves a gap) is P1, or add `ClipItem.kind='gap'`. Ripple delete is P0. |
| 02 | EXP-02/03/04, AAF | FCPXML moves to P1 (custom writer). EDL: we generate reel names ourselves, max 8 characters (fix "32 chars" in 06 §8.2). SRT only, VTT dropped. AAF is unsupported. |
| 02 | §8.5, 06 §8.1 | State that clip gain and fades are not carried in OTIO in the MVP. |
| 02 | P0 demotions (see §5 note) | RND-02 hardware encoders stay P0 (NVENC, QSV/VAAPI, AMF/VAAPI with libx264 fallback, see §0). Presets for the MVP: draft and youtube_1080p. PRV-02 live dissolve preview → P1 (rendered region instead). ANA-07 LLM → P1 (TF-IDF is the P0 path). TR-07 apply-all → P1. ING-03 thumbnails at one per 2 s, one peaks resolution. RND-04 HDR depends on Q2 (§4). |
| 03 | D-1 | Folder picking through `GET /fs/list`. Phase 3 shell: pywebview first. |
| 03 | D-2, §9 | Python 3.13. `fastapi.sse`. FFmpeg capability probe. |
| 03 | D-3 | Rule: the project document lives in Zustand and TanStack Query holds the server caches. Pin versions; TS ~6.0. |
| 03 | §3 `project/`, `jobs/` | Single command model (§1). Jobs: in-memory registry plus per-engine worker processes. No SQLite job table. |
| 03 | §4 | Namespace ids under `/projects/{pid}/…`. PATCH body = `{base_revision, commands[]}`, with commands addressed by id, not JSON Patch array indexes. Add `/fs/list`, SSE `Last-Event-ID`, and `GET /openapi.json` dumped by the CLI. |
| 03 | §8 | Repo `video-flow`. `justfile`. `schema.gen.ts`. `scripts/gen_samples.py`. Vite proxy. |
| 03 | §10 | Cookie authentication and a Host header check. |
| 04 | S4 | `Word.prob` is optional. Parakeet: merge tokens into words; each word ends at the next token's start, capped by the VAD range. Always pass a 16 kHz numpy array to engines (faster-whisper with PyAV 19 fails on file paths). |
| 04 | S9 | The unit is the utterance or sentence. The restart check compares against every utterance start in the block. Add a restart-cue lexicon (FR/EN). The gap values become tunable parameters. |
| 04 | §4.1 | Use local or semi-global alignment. A contained match means split the longer segment. False start = prefix match followed by a restart cue or a fuller take. Strip cue words before computing coverage. Use rapidfuzz on token-id lists. Thresholds are per model; use a top-k pre-filter, not an absolute cosine. Add the e5 `query:` prefix. |
| 04 | §4.2, §5 | VISUAL_DUPLICATE edges only between non-speech segments. |
| 04 | §4.3 | Onset envelope at 100 Hz, PSR ≥ 4, raw-audio refinement, offset plus drift. |
| 04 | §5 | Constrained average linkage. Must-links are merged first. |
| 04 | §7 | Consensus from complete takes only, with a tie rule for 2 takes. A missing metric is dropped and the weights renormalised. |
| 04 | §8 | Qwen3: thinking off. take_id = segmentId. |
| 04 | §10 | Proposals (cache) are separate from accepted beats (`project.json`). `reconcile()` matches by overlap. Any user decision locks the beat implicitly. |
| 05 | §1.3, §1.4 | ULID ids. Integer µs times and rational rates. Frame quantisation rule. Drop-frame display rule (show 29.97 as non-drop, with a note). |
| 05 | §2 | Bundle: remove `analysis.sqlite` as the store of record and replace it with `analysis/` (JSON/npy). `overrides` (transcript edits, orphan dismissals) live in `project.json`. |
| 05 | §3 | `Transition.afterItemId` plus the dormant rule. Overlay anchored to beatId or project time. Invariants for TakeRef status; `used` derived from `cut[]`. Score, flags and alignOffset leave `project.json`. `syncGroups[]`, `audioStreams[]`, `probe.video?`. `enabled=false` means removed with ripple. Blade: the left part keeps the id, the right part gets a new id, and the transition moves to the right part. Promote keeps audio settings and resets trims. |
| 05 | §4 | Replace the example with a complete, valid fixture that CI validates against the generated JSON Schema. |
| 05 | §6 | Exclude `revision` from determinism checks. A dormant transition compiles to a hard cut plus a warning. Debounce OTIO compilation (1 s of idle, and on export). |
| 05 | §8 | `extra='allow'` with a round-trip test. Unknown enum values are kept as opaque values. `app.minReader` makes older apps refuse to write. `pipelineVersion`. Each history line carries `schemaVersion`. |
| 06 | §3 | Offsets and durations are frame counts. `trim=end_frame` and `atrim=end_sample`, with `-t` only as a +0.5 s safety margin. Audio length follows the video frame count at concat. Fix the alignment text: start = left tail T; end = right head T; center = T/2 each. Graph-file flag chosen by the capability probe. Every labelled output must be mapped. |
| 06 | §6 | Loudnorm pass 1 runs on an audio-only graph variant. Silent input: skip loudnorm. Log `normalization_type`. |
| 06 | §8.2 | FCPXML via a custom writer. EDL fixes. OTIOZ needs real media. AAF unsupported. |
| 07 | §1 | Phase 1 P0 traceability table (add PRJ-04 inference, ING-04 duplicate skip, TL-12, the PRV-01 player, TR-07). Phase 0 list per §2.2. Phase 3: pywebview. |
| 07 | §2 | Risks: TS 7 / codegen, FFmpeg version spread, cloud-synced bundles, gated models, the 6-connection limit. |

---

## 4. Defaults assumed for open questions Q1–Q9 (07 §3), pending the user's answers

| Q | Default assumed | Consequence for the build |
|---|---|---|
| Q1 Machine | **Answered**: Windows and Linux; macOS dropped. NPU: Intel Core Ultra, AMD Ryzen AI, Qualcomm Snapdragon X. GPU: NVIDIA, Intel, AMD. | See §0: ONNX Runtime / OpenVINO for AI with NPU → GPU → CPU fallback; FFmpeg hwaccel + hardware encoders with libx264 fallback. |
| Q2 Cameras/audio | iPhone (HEVC, HLG possible, VFR) plus an occasional second camera or lav. | Proxies normalise VFR to CFR. HLG→SDR tone mapping (zscale+tonemap) in proxies and render as **P0-lite**: one fixed chain, no libplacebo. Sync groups exist in the schema only. |
| Q3 Language | French first, English sometimes. | Restart and filler lexicons for FR and EN. Multilingual models only. UI in English for now, with i18n hooks. |
| Q4 Outputs | YouTube 16:9 1080p. | Presets: draft and youtube_1080p. Nothing vertical. |
| Q5 Camtasia | Not the main finishing tool. | Camtasia stays in Phase 3. |
| Q6 Other editors | DaVinci Resolve first, then Premiere. | OTIO and EDL in the MVP. FCPXML is P1. |
| Q7 Volume | 20–60 rushes, 30–90 min in total. | n segments < 2000, so O(n²) pairwise work is fine. Render strategy A only. |
| Q8 Script | Usually none, sometimes an outline. | Heuristic clustering is the P0 path. Script-guided grouping stays in Phase 2. |
| Q9 Distribution | Personal tool, possibly open-sourced later. | Permissive licences only (MIT/Apache/BSD/CC-BY with credit). No gated models by default. GPL FFmpeg builds are acceptable as an external binary. |

---

## 5. Revised implementation plan (buildable and testable in this container)

Rules for every WP: tests run on CPU only, with synthetic media from FFmpeg lavfi (`testsrc2`, `mandelbrot`, `sine`, `anullsrc`, `flite`), no real rushes and no network in the unit tier. The test tiers are **unit** (no models), **smoke** (`-m smoke`, CPU models of about 300 MB or less, may download) and **bench** (Phase 0, not run here). Python 3.13 via uv. FFmpeg tests run on the system 6.1.1 build and must also pass with a static 7.x build when one is added. One commit per functional change, short functional message, no AI co-author trailer.

### 5.0 Shared contracts, fixed first (WP2 deliverable, reviewed before fan-out)

| Contract | Module | Content |
|---|---|---|
| Time | `videoflow/core/time.py` | `Rational`, `Micros` (int), `frames(us, rate)`, the quantisation rule, timecode formatting (non-drop) |
| IDs | `videoflow/core/ids.py` | `new_id(prefix) -> "seg_01J…"` (short ULID). Ids are never reused. |
| Project schema v1 | `videoflow/project/models.py` | Pydantic v2 models (`extra='allow'`): Project, Settings, Asset (`probe.video?`, `audioStreams[]`), SyncGroup, Beat, TakeRef, ClipItem, Transition(`afterItemId`), OverlayItem(anchor by beat or project time), Constraint, Overrides. A JSON Schema export, kept as a golden file. |
| Commands | `videoflow/project/commands.py` | A discriminated union of commands addressed by id. Each has `apply(project) -> (project', inverse)`, and every command is a pure function. |
| Store | `videoflow/project/store.py` | `Bundle(path)` gives the layout; `load`, `save_atomic`, `migrate`, `append_history`, `revision`. |
| FFmpeg | `videoflow/media/ffmpeg.py` | `FFmpegCaps` (version, `graph_flag`, xfade set, encoders, filters), `async run(args, on_progress, cancel) -> Result`, `probe(path) -> ProbeResult`. |
| Engines | `videoflow/engines/protocols.py` | `VadEngine`, `AsrEngine` (Word: text, start_us, end_us, `prob: float or None`), `TextEmbedder` (`model_id`, `encode`), `VisualEmbedder`, `ShotDetector`, `LlmLabeler`, each with a `Fake*` that replays fixtures. |
| Analysis types | `videoflow/analysis/types.py` | Utterance, Segment, Relation(kind, scores), Proposal(beats, edges), ThresholdProfile(model_id, …) |
| Resolved timeline | `videoflow/timeline/resolved.py` | `ResolvedTimeline` (integer frames; tracks V1/A1/V2; items with source ranges and handles; active and dormant transitions; warnings) |
| Jobs and events | `videoflow/jobs/types.py`, `videoflow/api/events.py` | `Job`, `JobState`, `submit/cancel/subscribe`; `Event` as a discriminated union (job.progress, job.done, asset.updated, project.updated) |

### 5.1 Work packages

| WP | Goal | Scope (files) | Depends on | Acceptance tests (in this container) | Size | Model |
|---|---|---|---|---|---|---|
| **WP1** Scaffold | Repo tooling | `backend/pyproject.toml` (uv, py 3.13, extras `[smoke]` and the accelerator extras of §0, torch from the CPU index), `scripts/install.{sh,ps1}`, `scripts/run.{sh,ps1}`, `docs/dependencies.md`, `.python-version`, `videoflow/__init__.py`, ruff/pytest/mypy config, root `justfile`, `.gitignore` (samples/, caches) | — | `scripts/install.sh` then `uv sync && just test` passes on an empty suite; `scripts/run.sh --help` works; `ruff check` is clean; `python -c "import videoflow"` works | S | haiku |
| **WP2** Core contracts and project model | §5.0 contracts plus project.json v1, migrations, bundle | `core/time.py`, `core/ids.py`, `project/{models,commands,store,migrations,schema}.py`, `tests/fixtures/project_v1_full.json` | WP1 | Property tests: frame quantisation does not drift over 300 clips at 25, 29.97 and 23.976. JSON Schema golden. Round trip keeps unknown fields and enums. Dummy v1→v2 migration plus `.bak`. Atomic save survives a simulated crash (kill between temp write and rename). `apply` then `inverse` gives the identical project for every command. Blade, promote and reorder follow the §3 rules (dormant transition, anchors). | L | opus |
| **WP3** FFmpeg toolkit | Capability probe, async runner, ffprobe | `media/ffmpeg.py`, `media/caps.py`, `hw/encoders.py` (detection only) | WP1 | Caps on 6.1.1 report `graph_flag=-filter_complex_script` and all xfade catalog names. Runner streams progress from `testsrc2` and cancel returns within 1 s. ffprobe parses rational fps, rotation and audio streams (including a file with no audio). | M | sonnet |
| **WP4** Sample generator | Deterministic synthetic rushes | `scripts/gen_samples.py`, `tests/conftest.py` (session fixture, cache by hash) | WP1 | Produces in 30 s or less: 720p25, 480p29.97 mono, vertical 1080x1920p24 with no audio, a VFR file, an HLG-tagged file, flite FR/EN retake scripts with 1 s gaps and a false start, a B-camera copy delayed 3.217 s with filtering, silence | S | sonnet |
| **WP5** Media service | Probe → Asset, proxies, thumbs, peaks, content hash | `media/{ingest,proxy,thumbs,peaks,hashing}.py` | WP2, WP3, WP4 | Ingesting the folder gives Assets with ids. A duplicate is skipped (ING-04). The proxy is CFR, 540p, H.264, with a keyframe every 1 s. HLG → SDR proxy has BT.709 tags. Thumbnails at 1 per 2 s, plus a sprite index. Peaks as `.bin` (single resolution) match an RMS reference within 1%. A second run is fully cached. | M | sonnet |
| **WP6** Resolved timeline | Derived main line → ResolvedTimeline | `timeline/{resolve,handles,validate}.py` | WP2 | Golden files from fixtures. Handle check for start, center and end, using the corrected semantics. Dormant transition after a reorder or exclude, with a warning. Excluded and disabled items ripple. Overlay anchor clamped. Total frames = Σ clip frames − Σ T frames. | L | opus |
| **WP7** OTIO compile and exporters | OTIO, OTIOZ, EDL, SRT, paper edit (FCPXML is a P1 stub) | `exporters/{otio_compile,otioz,edl,srt,paper_edit}.py` | WP6 (contract only, so it can start against the ResolvedTimeline fixture) | Golden `.otio` is deterministic once revision is excluded. The OTIO round trip keeps `videoflow` metadata. EDL: dissolve event correct, no spurious C event, reel names ≤8 characters with a mapping comment. OTIOZ with real sample files. SRT timings come from words. Paper edit is Markdown and CSV. | M | sonnet |
| **WP8** Render | Graph builder, presets, two-pass loudnorm, runner, validation | `render/{graph,presets,loudness,runner,validate}.py` | WP3, WP6 (contract) | Golden graph text and argument list. Render of the WP4 mixed inputs: video frames = expected exactly, audio duration = video duration ±1 frame. Integrated loudness −14 ±0.5 LUFS (ebur128). Silent input skips loudnorm. Audio-only pass-1 graph is valid. Cancel kills FFmpeg and removes the partial file. Frame-hash spot check at cut points. Works with the 6.1 flag, and with `-/filter_complex` when the probe allows it. | L | opus |
| **WP9** Jobs and stage cache | In-memory registry, priorities, workers | `jobs/{registry,workers}.py`, `analysis/cache.py` | WP2, WP3 | Priority ordering. Cancelling an FFmpeg job and an ML worker job (sleeping fake engine) completes in ≤1 s, and the worker respawns. The cache key is the hash of (input, stage version, params). Writes are atomic. Killing the process mid-stage and rerunning skips completed stages (NFR-04). Spawn-mode workers start with the `__main__` guard. | M | opus |
| **WP10** Analysis core (pure) | S9–S16 as pure functions | `analysis/{segment,textnorm,relations,align_tokens,cluster,intra_align,score,order,labels_tfidf,reconcile}.py` | WP2 (analysis types) | Golden tests on fixture words (FR/EN). The 1 s gap retake script gives the expected utterances and blocks. Restart cues split the false start. A contained match leads to a split, not PARTIAL. Constrained linkage never violates a cannot-link and is deterministic. A slider re-run on 2000 segments takes under 200 ms. Thresholds come from per-model profiles. Score renormalises when a metric is missing. `reconcile()` keeps user-locked beats. | L | opus |
| **WP11** Engines, smoke tier | Real CPU adapters behind the Protocols | `engines/vad/silero_onnx.py`, `engines/asr/{parakeet_onnx,faster_whisper}.py`, `engines/embed/onnx_st.py`, `engines/vision/{phash_hist,dinov2_onnx(opt)}.py`, `analysis/{shots,sync_gccphat}.py`, `engines/manifest.toml` | WP2 (protocols) | `-m smoke`: VAD finds the speech ranges in the flite sample. Parakeet/whisper-tiny words are merged with end times and `prob` may be None. Embeddings have dimension 384 and e5 gets its prefix. pHash separates near-duplicate from different shots. Scenedetect finds 3 of 3 cuts. GCC-PHAT lag 3.217 ±0.01 s with PSR ≥ 4; the shuffled control has PSR < 2. Manifest pins revisions and licences, and gated models are refused. | M | sonnet |
| **WP12** Pipeline orchestration | S0–S16 DAG on cache and jobs, producing proposals | `analysis/pipeline.py`, `analysis/stages.py` | WP5, WP9, WP10, WP11 (fakes enough for unit tests) | End to end on samples with Fake engines produces the expected beats. With smoke engines on 60 s of samples, the retake script groups the retakes into one beat. Changing the ASR engine reruns from S4 and the IoU remap keeps the TakeRefs. Progress events are emitted. | M | opus |
| **WP13** CLI | Headless `videoflow` | `cli.py` (Typer): `analyse`, `render`, `export`, `serve`, `dump-openapi`, `gen-samples`, `doctor` (caps) | WP5, WP7, WP8, WP12 | `videoflow analyse samples/ --engines fake` then `render` then `export --otio --edl` give valid files. `doctor` prints the FFmpeg caps. Exit codes are tested. | S | sonnet |
| **WP14** API | FastAPI app, SSE, cookie authentication, range serving | `api/{app,auth,routes_*,events,fs}.py` | WP2, WP5, WP9, WP12 (WP7/WP8 for the output routes) | httpx tests: no cookie gives 401; a wrong Host gives 403. `?token=` sets the cookie and redirects. PATCH with a stale `base_revision` gives 409. A command batch returns inverses. SSE resumes with `Last-Event-ID`. Range requests on a proxy give 206. `/fs/list` refuses paths outside the roots. `dump-openapi` is stable and the event union is in the schemas. | L | sonnet |
| **WP15** Frontend foundation | Vite 8, React 19.3, TS ~6.0, codegen, stores, undo | `frontend/` scaffold, `src/api/schema.gen.ts`, `src/api/client.ts` (openapi-fetch + react-query), `src/state/{project,commands,undo,events}.ts` | WP14 (openapi.json) | `pnpm typecheck` and `vitest`: the undo stack applies the server inverses; drags are grouped into one gesture; a 409 triggers rebase. The codegen check in CI shows no diff. Playwright smoke against `videoflow serve` with fixtures loads the project. | M | sonnet |
| **WP16a** Bin, inspector, output panels | Standard UI | `features/{bin,inspector,output}/` | WP15 | Vitest plus Playwright: import a folder via `/fs/list`, jobs progress over SSE, render and export buttons produce files | M | sonnet |
| **WP16b** Branch timeline (canvas) | Branch/Cut lanes, trims with word and shot snapping, blade, ripple, transitions | `features/branch-timeline/` | WP15, WP6 semantics | Unit tests on the hit-testing and snapping maths. Playwright: trim snaps to a word boundary, promote, undo. A perf test with 300 clips runs at ≥55 fps in headless Chromium (indicative only). | L | opus |
| **WP16c** Player and compare | Double-buffered cut player, N synchronised players | `features/{player,compare}/` | WP15, WP14 range serving | Playwright: the cut player crosses 3 clips with no gap more than 1 frame (measured with `requestVideoFrameCallback`). Compare with 4 players plus SSE does not stall (or the cap is applied). | L | opus |

### 5.2 Ordering and parallelism

```
WP1 ─┬─ WP2 (contracts; review gate) ─┬─ WP5 ──────────────┐
     ├─ WP3 ──────────────────────────┤  WP6 ─┬─ WP7       │
     └─ WP4 ──────────────────────────┘  WP9  ├─ WP8       ├─ WP12 ─ WP13 ─ WP14 ─ WP15 ─┬─ WP16a
                                         WP10 │            │                              ├─ WP16b
                                         WP11 ┘────────────┘                              └─ WP16c
```

| Wave | Parallel WPs (disjoint files) | Notes |
|---|---|---|
| 0 | WP1 | — |
| 1 | WP2 ‖ WP3 ‖ WP4 | WP2 freezes the §5.0 contracts. WP3 owns `media/ffmpeg.py` and `media/caps.py`. WP4 owns `scripts/` and `conftest`. |
| 2 | WP5 ‖ WP6 ‖ WP9 ‖ WP10 ‖ WP11 | Disjoint packages: `media/`, `timeline/`, `jobs/` and `analysis/cache.py`, `analysis/*` (pure), and `engines/` with `analysis/{shots,sync_gccphat}`. Only WP9 touches `analysis/cache.py`. |
| 3 | WP7 ‖ WP8 ‖ WP12 | `exporters/`, `render/`, `analysis/pipeline.py` |
| 4 | WP13 → WP14 | The CLI before the API (Phase 0 needs a headless run) |
| 5 | WP15 | Codegen gate |
| 6 | WP16a ‖ WP16b ‖ WP16c | Separate `features/` folders. Shared state comes only through `src/state` (frozen in WP15). |

Merge discipline: one branch per WP. Contract changes after WP2 need an explicit contract PR before the dependent WPs continue. CI runs `just test` (unit), plus `just smoke` in nightly or manual runs.

### 5.3 Not buildable or verifiable here (left to Phase 0 or 3)

Real-rush accuracy and thresholds (§2.2), NPU execution providers (OpenVINO NPU, VitisAI, QNN), GPU encoders and decoders (NVENC, QSV, AMF, VAAPI), Windows-specific runs, the custom FCPXML writer validated in FCP and Resolve, interop smoke tests in real NLEs, pywebview packaging, and the LLM labeler (Ollama is not in the container; the P0 path is TF-IDF).

### 5.4 Commit convention

Resolved by the user: one commit per functional change, short functional message, no AI co-author trailer.
