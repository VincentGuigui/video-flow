# Projects and working folders — 2026-11-01

## Where projects live

- A project is a `<name>.video-flow` folder **inside the user's working folder**, the folder that holds the original videos and media. It contains `project.json` (the edit), `history.jsonl`, `analysis/`, `features/`, `exports/` and `renders/`.
- Media are referenced **relative to the working folder** (`relPath`, with the absolute path kept as a fallback): copying or moving the whole working folder (media and project) to another place, disk or computer keeps the project working. Media outside the working folder are referenced with `../` paths, or only absolutely when they are on another Windows drive.
- Rebuildable caches (proxies, thumbnails, waveforms, title pictures, render work files) are not in the project: they live in the application cache (`cache/<project id>/` beside the executable), shown and cleared in Settings (see [workspace zones](workspace-zones.md)).
- The application keeps only a list of recent projects (`recent-projects.json` beside the executable, at most 20, most recent first). Projects created by earlier versions in the per-user `Video-Flow` library (`*.videoflow`) are added to that list the first time, and open as before.

## Home page

The logo closes the open project (its workers, renders and media are released and the editor is cleared) and shows the home page; there is no way back without opening or creating a project.

- **New project**: a name and a working folder (chosen with the native folder dialog in the desktop app, typed in a browser) create `<working folder>/<name>.video-flow` and open it. Names are kept file-system safe (`< > : " / \ | ? *` removed); an existing folder of that name is refused.
- **Open project…**: opens a `.video-flow` folder chosen natively (or typed in a browser) and puts it first in the recent list.
- **Recent projects**: each line shows the name and the working folder, with **Open**, **Rename** (renames the project and its folder to `<new name>.video-flow` in the same working folder) and **Remove from list** (forgets it here; its folder and media are kept).

## Launch, Save and Save as

- The desktop app reopens the most recent project of the list; with none, it starts on the home page. `videoflow desktop --project PATH` opens or creates a given folder.
- Save names an untitled project (renaming its folder); **Save as** copies the project into the same working folder as `<new name>.video-flow` (decisions, analysis and features; media references stay relative) and opens the copy. The window title shows the open project.

## Security

The interface never names folders itself in the desktop app: the native folder dialog issues a single-use handle (`POST /api/desktop/folder`, desktop secret only) for a working folder or a project folder (one that holds `project.json`), which the project action redeems. In a browser, typed folders must be under a `--media-root`.

Validation: backend tests cover folder naming, Save as beside the original with relative media, rename moving the folder and updating the list, the recent list order and removal (files kept), media following a copied working folder, native folder handles (desktop secret required, single use, project folders only for Open), close and reopen. A browser check created a project in one working folder, imported media (stored as `talk.mp4` relative), created a second project in another folder from the home page, reopened the first by its folder, and listed both caches in Settings.
