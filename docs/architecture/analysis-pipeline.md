# Analysis pipeline

Analysis turns an imported source into timecoded words, a summary, keywords and topic sections, then uses them to stack retakes. It runs inside the editor's import queue, one file at a time, on the local machine. Behaviour is specified in [interactive editor](../features/interactive-editor.md), [transcript panel](../features/transcript-panel.md), [retake grouping](../features/retake-grouping.md) and [editor refinements](../features/editor-refinements.md); this page maps it to code. See [overview](overview.md) for the process layout and [data model](data-model.md) for the bundle.

## 1. What is wired where

| Part | Code | Reached from |
|------|------|--------------|
| Import queue: probe, hash, proxy, analysis, grouping, publish | `editor/imports.py` | Editor API (`api/app.py`), every import |
| Sidecar format, reuse and storage; deterministic summary and keywords | `editor/analysis.py` | Import queue; `GET /api/analysis/{asset}`; `POST /api/export` (SRT, paper edit) |
| Sentences, topics, extractive summary | `editor/topics.py` | `describe()` and the Qwen worker method |
| Retake grouping | `editor/grouping.py` | Import queue, new non-duplicate clips only |
| VAD, ASR, text embedder, Qwen | `engines/` | The `transcriber` worker (`editor.analysis.Transcriber`) |
| Device selection NPU → GPU → CPU | `hw/ai.py` | Every ONNX session |
| Beat pipeline S9–S16: `analysis/segment`, `relations`, `cluster`, `align_tokens`, `intra_align`, `score`, `labels_tfidf`, `order`, `reconcile`, `cache` | `analysis/` | **Tests only** (`tests/analysis/`, golden run in `test_golden_pipeline.py`). No CLI command, API route or job calls it |
| Shots (PySceneDetect), DINOv2, pHash/histogram, GCC-PHAT sync | `analysis/shots.py`, `engines/vision/`, `analysis/sync_gccphat.py` | **Tests only**; registered in `engines/registry.py` but never created outside tests |

Only `analysis/types.py` (`Word`, `Transcript`, `EngineInfo`) and `analysis/textnorm.py` (accent folding, filler list for SRT) are used by the editor path. The CLI (`cli.py`) has `desktop`, `serve`, `export` and `version`; none runs analysis. Imports use the worker processes of `jobs/workers.py`, not the job registry of `jobs/registry.py`.

Not implemented at all: timestamp refinement (WhisperX), audio features (EBU R128 loudness, clipping, noise floor), frame quality metrics, and LLM beat labels (`LlmLabeler` exists only as a protocol with a fake). The editor has no beats, beat order, default take selection or sensitivity slider.

## 2. Import flow

`Imports._run` processes one file under a lock (sequential queue). Each job reports `state`, `phase` and `progress`.

| Step | Phase shown | What happens |
|------|-------------|--------------|
| 1 | Reading media | `media.ingest.ingest_files`: ffprobe and content hash (BLAKE2b; whole file up to 64 MiB, otherwise size + 16 sampled 1 MiB chunks). A known hash is a duplicate: a skip-analysis import ends as "Already imported" |
| 2 | Preparing playback | `media.proxy.build_proxy`: 540p proxy in `cache/proxies/`, keyed by content hash, proxy version and height |
| 3 | Checking analysis JSON | Analysed imports only: `load_analysis` looks for a reusable sidecar (§4). A hit skips steps 4–7 (`cached = true`) |
| 4 | Download missing models in Settings, or cancel import | Uncached source with audio: state `waiting-models` while any model of `required_models(preferences)` is not up to date (polled every 0.35 s). Nothing downloads implicitly |
| 5 | Loading speech models / transcribing | FFmpeg extracts 16 kHz mono float32 PCM to `cache/<job>.f32` (deleted afterwards); the worker runs VAD then ASR; `describe()` builds words, deterministic summary, keywords and topics |
| 6 | Summarizing / Titling topics with local Qwen | Only when the summary engine is `qwen` and the transcript has words: Qwen replaces summary and keywords, then retitles the topics |
| 7 | — | `store_analysis` writes the bundle cache, then the sidecar (§4). A source without audio gets an empty analysis without loading any model |
| 8 | Matching retakes | New clips with words: `_match` (§6) |
| 9 | Adding to flow / Ready | `_publish` commits `AddAsset` + `SetEditor` as one undo step: linked video/audio clips at the matched clip's start on a new top layer, or appended |

A duplicate imported with analysis gets its analysis created or reused but is neither re-published nor regrouped. Waveform peaks and thumbnails are not part of import; the API builds them on first request. A failure marks the job `failed` and the queue continues; cancelling cancels the task and kills the worker process.

## 3. Engines and devices

All ML runs in one long-lived `transcriber` worker process (`jobs.workers.WorkerPool`, spawn start method, 900 s start timeout). Engines load lazily on first call, so grouping cached analyses never loads speech models. Cancelling a call kills the process; a new one is spawned. Preferences (`settings.json` in the application folder, `preferences.py`) are read when the queue is created; Settings refuses changes while imports run, then rebuilds the queue and its worker.

| Preference | Values (default) | Effect |
|------------|------------------|--------|
| `asrEngine` | `parakeet`, `faster-whisper` (`parakeet`) | ASR adapter |
| `summaryEngine` | `deterministic`, `qwen` (`deterministic`) | Summary, keywords and topic titles |
| `aiDevice` | `auto`, `npu`, `gpu`, `cpu` (`auto`) | First tier of the ONNX provider chain |
| `analyseImports` | bool (`true`) | Default of the analyse/skip choice |

**Provider chain** (`hw/ai.py`): NPU (OpenVINO `NPU`, VitisAI, QNN) → GPU (CUDA, DirectML, OpenVINO `GPU`, ROCm, MIGraphX) → CPU. `auto` and `npu` start at the NPU, `gpu` skips it, `cpu` uses only the CPU. `make_session` walks the chain per model: a provider must become active and pass a warm-up run, otherwise the next one is tried, so one model's unsupported operator does not demote the others.

| Engine | Code | Device and behaviour |
|--------|------|----------------------|
| Silero VAD v5 | `engines/vad/silero_onnx.py` | Chain. 512-sample windows at 16 kHz; speech on at ≥ 0.5, off below 0.35; ranges ≥ 0.25 s; silences < 0.1 s merged; 30 ms padding |
| Parakeet TDT 0.6B v3 int8 | `engines/asr/parakeet_onnx.py` (onnx-asr) | Encoder on the chain, decoder/joint pinned to CPU. Tokens merged into words; a word ends at the next word's start, at most 0.6 s after its last token; no word probability |
| faster-whisper tiny | `engines/asr/faster_whisper.py` | CUDA (float16) when available and `aiDevice` ≠ `cpu`, else CPU int8; no NPU. Word probabilities; verbatim filler prompt for FR/EN; `condition_on_previous_text` off |
| MiniLM-L12 sentence embedder | `engines/embed/onnx_st.py` | Chain. Mean pooling, L2-normalised, 384 dims, 128 tokens max, batches of 32 |
| Qwen2.5 0.5B Instruct | `engines/summary.py` (transformers + torch) | CPU only, ≤ 4 threads, greedy decoding, local files only |

**ASR chunking** (`engines/asr/chunks.py`, both adapters): VAD ranges are padded by 0.3 s, merged when less than 0.6 s apart, and cut into chunks of at most 30 s at the quietest 20 ms frame within 3 s of the limit. Chunks under 50 ms are skipped. Word times are mapped back to source microseconds. ASR receives the project language (default `fr`).

**Qwen**: the summary prompt asks for JSON (`summary`, up to 12 `keywords`); transcripts over 2,800 tokens are reduced to their first and last 1,400 (`summaryScope` records this). An unparseable summary fails the import. Topic titles use the first 1,200 tokens of each section and keep at most five words; a failed title falls back to the keyword title.

## 4. Sidecar and analysis cache

`AnalysisFile` (version 1): `sourceHash`, `words` (text, `startUs`, `endUs`, optional `prob`), `summary`, `keywords`, `language`, `summaryEngine`, `summaryScope`, `topics`, `topicsEngine`.

**Reuse** (`load_analysis`), in order:

1. `<source stem>.json`, then `<source name>.json` (e.g. `clip.mp4.json`) beside the source: accepted when it is a JSON object with `words`, version 1, and a `sourceHash` equal to the asset hash or absent (hand-written sidecars).
2. Bundle cache `analysis/sidecars/<sha256(content hash)>.json`: accepted when the version is 1 and `sourceHash` matches exactly.

Sidecars without topics get them derived deterministically on load; the file is not rewritten.

**Storage** (`store_analysis`): the bundle cache is always written first (atomically). Then `<source stem>.json` is written atomically beside the source, never over an existing file. If that fails (read-only folder, unrelated JSON already there), the job keeps the cache copy and shows a warning.

## 5. Sentences, summary, keywords, topics

`editor/topics.py`, deterministic unless Qwen is selected.

- **Sentences**: split after `.`, `!`, `?` or `…`, before a pause ≥ 0.7 s, or at 30 words.
- **Content words**: case- and accent-folded, longer than 3 characters, not digits, not in the FR/EN stop list (which includes fillers).
- **Summary**: sentences ranked by summed content-word frequency over √(content words); up to two kept, in spoken order, within 280 characters.
- **Keywords**: the 12 most frequent words longer than 3 characters outside a short stop list.
- **Topics** (TextTiling-style): no split when the clip spans less than 30 s. Each gap between sentences scores `1 − cosine(words of the 3 sentences before, 3 after) + 0.5 × min(pause / 2 s, 1)`. A boundary needs a score ≥ max(0.6, mean + 0.5 × standard deviation); candidates are taken from the highest score down and kept only if every topic stays ≥ 15 s; at most 12 topics.
- **Titles**: up to five content words weighted by count × log(1 + sections / sections containing the word), in order of first use, original spelling, first letter capitalised.

## 6. Retake grouping

`editor/grouping.py`, run by `Imports._match` for a new (non-duplicate) clip with words.

| Constant | Value | Meaning |
|----------|-------|---------|
| `SENTENCE_MATCH` | 0.68 | Two sentences match when `0.5 × cosine + 0.5 × word overlap` reaches it |
| `LEXICAL_MATCH` | 0.60 | Threshold on word overlap alone when vectors are unavailable |
| `MIN_COVERAGE` | 0.5 | Minimum retake score for stacking |

- Sentences of two words or more are compared; word overlap is rapidfuzz `token_set_ratio` on case-folded text.
- `coverage(A, B)` is the share of A's words in sentences that match some sentence of B. Retake score = max(coverage A→B, coverage B→A), so a partial retake matches its full take either way.
- Candidates are assets that have a clip in the edit and a reusable analysis with words. The best score ≥ 0.5 wins; the new clip goes at that clip's start (its video clip if any) on a new top layer.
- Vectors are used only when MiniLM is up to date in `models/`. Uncached analysed imports already wait for it (it is in `required_models`), so the word-overlap fallback applies to imports that reused a sidecar while the model is missing.
- **Vector cache**: `features/sentences/<sha256("<content hash>:paraphrase-multilingual-minilm-l12-v2")>.npy`, float32, reused when its row count equals the sentence count, otherwise recomputed in the worker and saved atomically.

## 7. Models

Pinned in `engines/manifest.toml` (Hugging Face repo, 40-hex commit, licence, files). `manifest.py` refuses gated repos, unpinned revisions and licences outside MIT, Apache-2.0, BSD-2/3-Clause, CC-BY-4.0 and CC0. Files live in the application `models/hf/` cache. `downloads.py` reports Missing / Obsolete / Up to date per model and downloads only on an explicit Settings request, in a cancellable worker; models with `in_editor = false` are hidden there and refused.

| Key | Purpose | Used by | Required when |
|-----|---------|---------|---------------|
| `silero-vad` | Speech ranges before ASR | Import | Always |
| `parakeet-tdt-0.6b-v3-int8` | ASR with word times (default) | Import | `asrEngine = parakeet` |
| `faster-whisper-tiny` | ASR alternative (`whisper` extra) | Import | `asrEngine = faster-whisper` |
| `paraphrase-multilingual-minilm-l12-v2` | Sentence vectors for retake grouping | Import | Always |
| `qwen2.5-0.5b-instruct` | Summary, keywords, topic titles (`qwen` extra) | Import | `summaryEngine = qwen` |
| `dinov2-small` | Visual embeddings (`in_editor = false`) | Tests only | Never |

Versions and licences: [dependencies](../reference/dependencies.md).

## 8. Beat pipeline (not wired)

The `analysis/` modules implement the original beat model as tested library code. They work on in-memory words and segments; nothing in the application produces their inputs or consumes their output.

| Module | Stage | Main defaults |
|--------|-------|---------------|
| `segment.py` | Speech and visual segments, restart detection | utterance gap 0.8 s, sentence gap 0.4 s, block gap 2.0 s, shot gap 0.5 s, restart coverage 0.7 on the first 5 content tokens; visual segments 1.5–20 s |
| `relations.py`, `align_tokens.py` | RETAKE, PARTIAL_RETAKE, split suggestions, visual and simultaneous relations | per-model `ThresholdProfile`: θ_text 0.55, min coverage 0.5, lexical weight 0.6, partial coverage 0.8 at ≤ 0.6 × length, θ_vis 0.85; MiniLM cosine floor 0.2 |
| `sync_gccphat.py` | Audio offset between simultaneous recordings | onset envelope at 100 Hz, 200–3400 Hz band, peak-to-sidelobe ≥ 4 |
| `cluster.py` | Constrained average linkage into beats | τ 0.5 at sensitivity 0.5, range 0.05–0.95; SIMULTANEOUS pairs contracted |
| `intra_align.py` | Anchors between takes (tokens, DTW, sync) | — |
| `score.py` | Take score | completeness 0.30, fluency 0.20, audio 0.15, video 0.15, confidence 0.10, recency 0.10; false start × 0.3 |
| `labels_tfidf.py` | Beat labels by TF-IDF | — |
| `order.py` | Beat order and default take | — |
| `reconcile.py` | Merge proposals into `project.json` beats, keeping locked ones | — |
| `cache.py` | Stage cache `<root>/<stage>/<key>/`; key = BLAKE2b-128 of (inputs, stage, version, params); atomic directory rename | — |
