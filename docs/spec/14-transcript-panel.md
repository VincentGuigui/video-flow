# 14. Transcript panel and topic sections — 2026-10-26

This revision supplements 09 (import and analysis) and 11 (local AI settings).

## Analysis output

An analysed import produces, in addition to the timecoded words:

- **Summary**: a short summary of the whole clip. The deterministic engine picks up to two representative sentences, at most 280 characters, in spoken order. Local Qwen writes the summary when selected in Settings.
- **Topics**: consecutive sections of the clip, each with a start and end time (integer microseconds, source time), a title of at most five words, and its transcript sentences.
  - Sentences split on end punctuation, pauses of 0.7 s or more, or 30 words.
  - A topic boundary needs a clear drop in vocabulary overlap between the three sentences before and after it, or a long pause. Every topic lasts at least 15 s; there are at most 12 per clip. Clips under 30 s, or about one subject, have a single topic.
  - Titles are the five words most specific to the section, in spoken order. With Qwen selected, Qwen writes each title, falling back to the keyword title if it fails.

The sidecar JSON (09) gains `topics` and `topicsEngine`; its version stays 1. Older sidecars without topics get them on load, deterministically, without rewriting the file.

## Transcript panel

- Properties shows a **Transcript** tab next to Clip and Project, only while a clip is selected. It reads the selected clip's source analysis.
- It shows the summary, then the list of topics: start – end timecodes and the title.
- Clicking a topic expands it to its transcript lines, each with a timecode, and highlights the topic's range on the assembly timeline. Clicking it again collapses it and removes the highlight. Changing the selected clip also removes the highlight.
- Clicking any timecode (topic start/end or transcript line) moves the timeline cursor there and stops playback.
- Timecodes are assembly times, mapped through the clip's position and trim. Times outside the clip's trimmed range, or on a disabled clip, show the source time greyed out and do not move the cursor. The highlight is clamped to the trimmed range.
- Media without analysis shows a hint to import it again with analysis.

Validation: backend tests cover sentence splitting, two-subject segmentation with timecodes, single-subject stability, title length and LLM fallback, summary length and topics derived for old sidecars. Frontend tests cover source-to-assembly mapping with trims, disabled clips and range clamping. A browser check on a served project confirmed topics, expansion, highlight and cursor seeks.
