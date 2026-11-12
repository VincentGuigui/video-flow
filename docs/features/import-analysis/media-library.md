# Project media

The **Project media** list, on the left of the editor, shows every medium you imported, with a thumbnail, its duration (or **Image**), its size, and whether it is ready or offline. Hover a card for two seconds to see the topics of its transcript, when it has one.

**Right-click** a medium to select it and open its menu: **Info** and **Analysis…**. Selecting several media (Ctrl + click) and pressing Delete removes them ([selecting and deleting](../editing/workspace-zones.md)).

## Info

A window with the file size (or "Offline"), duration, picture size, and whether it has sound, then:

- **Location**: the full path. Click it to show the file in your file manager. Below it, the path relative to the working folder ([projects](../getting-started/projects.md)).
- **Analysis**: the number of words and topics, the engine that made the summary, the summary, a link that shows the analysis file, and **Show transcript**, which selects a clip of that medium and opens the Transcript tab.

## Analysis…

Analyses the medium again, in the same window as an import, with the same progress, cancel and missing-model prompt. **Analyse** transcribes it again and writes a new summary, keywords and topics, **replacing** its analysis file (the one next to the medium, and the project's copy). It is refused while the medium is offline.

The clips already in the edit stay. If the new analysis shows that the medium is a retake of another clip, and the medium has a single clip (or one linked picture and audio) not already stacked over that retake, the clip moves onto a new lane over it — one undo step. With several clips of the medium, the edit is left as it is.

## Technical notes

Endpoints and rules: [editor behaviour](../../architecture/editor-behaviour.md#project-media-menu). Tests: [validation record](../../validation/2026-11-12-manual-pages.md#project-media-menu).
