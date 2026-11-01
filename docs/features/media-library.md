# Project media: context menu, info and re-analysis — 2026-11-01

Right-clicking a medium in Project media selects it and opens a menu with **Analysis…** and **Info**.

## Info

A dialog with the file size (or "Offline"), duration, picture size, whether it has audio, and:

- **Location**: the full path; clicking it shows the file selected in the system file manager (Explorer `/select` on Windows; the containing folder through `xdg-open` on Linux). The path relative to the working folder is shown below it ([projects](projects.md)).
- **Analysis**: word and topic counts, summary engine and summary, a link that shows the analysis JSON (the sidecar beside the media, else the project's cached copy) in the file manager, and **Show transcript**, which selects a clip of that medium and opens the Transcript tab.

`GET /api/assets/{id}/info` returns these facts; `POST /api/assets/{id}/reveal?target=media|analysis` shows a file.

## Analysis…

Opens the import dialog in re-analysis mode: the same progress, cancellation and missing-model prompt as an import. **Analyse** transcribes the medium again and writes a new summary, keywords and topics, replacing its analysis JSON (the sidecar beside the media is overwritten; the project's cached copy too). `POST /api/assets/{id}/analyse` starts it as an import job that ignores any existing analysis; it is refused while the medium is offline. Clips already in the edit are kept. When the new analysis matches another clip's media (same rule as on import, see [retake grouping](retake-grouping.md)) and the medium has a single clip (or one linked pair) in the edit that is not already over that retake, the clip moves onto a new lane at the matched clip's position; this is one undo step. Several clips of the medium leave the edit unchanged.

Validation: a backend test covers the info facts before and after an analysis exists, revealing the media and its JSON, and a re-analysis that does not reuse the existing JSON. A browser check opened the menu, the Info dialog (size, duration, relative path, analysis summary), Show transcript, and started a re-analysis that transcribed again instead of reusing the JSON.
