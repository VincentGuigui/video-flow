# Retake grouping

When you import an analysed file ([importing media](importing.md)), Video-Flow looks for an earlier clip in which the **same sentences** are said, and stacks the new clip over it on a new lane, at the same position. The takes then appear in [Compare takes](../editing/compare-takes.md). If nothing matches, the clip is added at the end.

## How it decides

It compares what is said, not the words one by one: two sentences match when they say the same thing in different words (fillers, rewording, hesitations). A partial retake matches its full take, in either order. The best match, above a minimum score, wins.

This needs the **MiniLM** model (a small multilingual text model, downloaded on request in [AI models and components](../getting-started/ai-models.md)). While it is missing, grouping falls back on comparing the words themselves, which works well on clear retakes but less so on rewording. Importing without analysis never groups.

## When it is wrong

Grouping is a suggestion: drag the clip to another lane, or move it away. **Analysing a medium again** applies the same rule and moves its clip over its retake when there is only one candidate ([project media](media-library.md)).

## Technical notes

The model choice, its benchmark against other models, the scoring formula and the thresholds are in [analysis pipeline](../../architecture/analysis-pipeline.md#retake-grouping). The thresholds were set on a synthetic benchmark and still have to be confirmed on real rushes. Tests: [validation record](../../validation/2026-11-12-manual-pages.md#retake-grouping).
