# Text search

Find where a word or a phrase is said in the edit, and jump from one occurrence to the next.

## Searching

1. Click the search box in the header (**Search what is said**), or press **Ctrl + F**.
2. Type a word or a few words. Case, accents and punctuation do not matter, and the last word may be incomplete: `proj` finds "projet" and "project".
3. The clips where the text is said are outlined in the clip flow, and a vertical line marks each occurrence inside them (on the video clip and on its audio). The box shows the number of occurrences, and which one the cursor is on (`2 / 4`).

Only what is said inside the kept part of a clip counts: words in trimmed parts, in disabled clips, in pictures and freeze frames are not found. Clips without a transcript (imported without analysis) are not searched; analyse them from the [media list](../import-analysis/media-library.md).

## Moving between occurrences

- **Enter**, or the down arrow of the box: move the cursor to the next occurrence. Each Enter goes one further; after the last one it starts again at the first.
- **Shift + Enter**, or the up arrow: the previous occurrence.
- The timeline scrolls to show the cursor. If a clip is focused and the occurrence is in another clip, the focus is left.
- **Escape** clears the box; **Escape** again leaves it. The **×** button clears it too.

## Technical notes

Rules and code are in [editor behaviour](../../architecture/editor-behaviour.md#text-search); tests in the [text search validation](../../validation/2026-11-12-text-search.md).
