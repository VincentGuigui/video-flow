# Transcript panel

The **Transcript** tab of the properties panel shows what was said in the selected clip, with its summary and topics, and lets you correct the words. It appears next to Clip and Project while a clip is selected, and reads the analysis of the clip's file ([importing media](importing.md); engines: [AI models and components](../getting-started/ai-models.md)). A clip without analysis shows a hint to import it again with analysis.

## Summary and topics

An analysed import gives, besides the timed words:

- a **summary** of the clip, in one or two sentences;
- **topics**: consecutive sections of the clip, each with its start and end time, a title of up to five words, and its sentences. A short clip, or one about a single subject, has one topic.

## Using the transcript

- **Click a topic** to open its sentences, with a timecode on each, and set the timeline range to it ([range and trim](../editing/range-and-trim.md)); click again to close it and reset the range.
- **Click a word** to set the range to it, **Shift + click** another word to extend it; or select text across several lines.
- **Click a timecode** to move the cursor there and stop playback.
- Timecodes are positions in the edit. Times outside the kept part of the clip, or on a disabled clip, show the original time greyed out and do not move the cursor.

## Correcting words

Double-click a word to edit it in place; press **Enter** or leave the field to save, **Esc** to cancel. The word keeps its timing, and the sentence text updates. Corrections are saved in the analysis file, so they follow the medium. Your original media are never changed.

## Technical notes

How topics and summaries are made, the analysis file and the correction rules: [analysis pipeline](../../architecture/analysis-pipeline.md#summary-and-topics). Tests: [validation record](../../validation/2026-11-12-manual-pages.md#transcript-panel).
