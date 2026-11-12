# Validation: text search

Behaviour: [text search](../features/editing/text-search.md). Rules: [editor behaviour](../architecture/editor-behaviour.md#text-search).

## Tests

`frontend/src/search.test.ts` covers normalisation (case, accents, punctuation), phrase matching with a prefix on the last term, placement in the assembly through the clip trim (occurrences outside the kept range, in disabled clips and in freeze frames left out), a linked video and audio searched once and both marked, and next / previous with wrapping.

## Browser check

A served project with French transcripts on two sources (one used by two clips) and a freeze frame of one of them: Ctrl + F focused the box; typing `pro` found 3 occurrences (4 before freeze frames were excluded), outlined the clips and drew the marks on video and audio clips, not on the freeze frame; Enter moved the cursor to occurrences 1 then 2, Shift + Enter back to 1, the arrow buttons likewise; `zzz` showed "No match" and removed the outlines; Escape cleared the box.
