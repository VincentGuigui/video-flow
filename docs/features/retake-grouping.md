# 18. Retake grouping with sentence similarity — 2026-10-28

This revision replaces the transcript/keyword similarity of 09 ("Import and analysis") used to place a new clip over an earlier take.

## Model choice

One text embedder is kept: **paraphrase-multilingual-MiniLM-L12-v2** (Apache-2.0, 118 MB uint8 ONNX, ~3–5 ms per sentence on CPU). multilingual-e5-small is removed from the manifest and code.

Benchmark: `backend/tests/fixtures/retake_pairs.json`, 34 retake pairs (fillers, rewording, reordering, truncation; mostly French, some English) and 36 hard negatives from the same unboxing context, sharing vocabulary on purpose.

| Scorer | AUC | Best accuracy | Positive mean / negative mean |
|--------|-----|---------------|-------------------------------|
| Word overlap only (`token_set_ratio`) | 0.996 | 0.986 | 0.85 / 0.47 |
| multilingual-e5-small | 0.996 | 0.971 | 0.97 / 0.88 (compressed scale) |
| multilingual-e5-base (279 MB) | 0.990 | 0.971 | 0.96 / 0.85 |
| paraphrase-multilingual-mpnet-base-v2 (279 MB) | 0.988 | 0.986 | 0.92 / 0.45 |
| **MiniLM-L12** | 0.980 | 0.971 | 0.88 / 0.40 |
| **MiniLM-L12 + word overlap (50/50)** | **1.000** | **1.000** | 0.86 / 0.43 |
| mpnet-base + word overlap | 1.000 | 1.000 | 0.88 / 0.46 |

MiniLM blended with word overlap separates every pair, like mpnet, at 2.4× less size and CPU time; its cosine scale leaves room between classes, unlike e5. The benchmark is synthetic: thresholds must be confirmed on real rushes.

## Algorithm

- Sentences: the transcript split as in 14 (punctuation, pauses ≥ 0.7 s, 30 words), keeping sentences of two words or more.
- Two sentences match when `0.5 × cosine + 0.5 × word overlap ≥ 0.68`. Without vectors (model not downloaded), word overlap alone must reach 0.60.
- Coverage of clip A in clip B: share of A's words in sentences that match some sentence of B. Retake score = max(coverage A→B, B→A), so a partial retake matches its full take in either order.
- On analysed import, the new clip is compared with every clip already in the edit that has a transcript; the best score ≥ 0.5 wins. The new clip is placed at that clip's position on a new lane (its video clip if it has one), so it appears in Compare takes (16). Otherwise it is appended.
- Sentence vectors are computed in the import worker and cached per source in `features/sentences/` of the bundle; the speech engines are not loaded for that. No model is downloaded implicitly: the model is required in Settings, and grouping falls back to word overlap while it is missing.

Validation: unit tests cover matching and non-matching clips, partial retakes, the effect of vectors on a borderline lexical match, the vector cache, and the word-overlap threshold on the benchmark (≥ 95 %). A smoke test checks the MiniLM blend on the benchmark (≥ 97 %; measured 100 %). An API test imports a take, an unrelated clip and a retake, and checks that the retake is stacked over the take.
