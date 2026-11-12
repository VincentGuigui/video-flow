# Projects and working folders

## Where projects live

A project is a folder named `<name>.video-flow`, created **inside your working folder**: the folder that holds your original videos and media. It holds your edit and analysis. Your media are never copied into it.

Media are remembered by their position **relative to the working folder**. You can therefore copy or move the whole working folder (media and project) to another place, disk or computer, and the project keeps working. Media that live outside the working folder are referenced by their path.

Previews, thumbnails and other things Video-Flow can rebuild are not stored in the project but in a cache next to the application, managed in Settings ([cache](../editing/workspace-zones.md#cache)). Video-Flow also remembers, per user, the list of your recent projects.

## Home page

Click the **logo** to close the open project and go to the home page. From there:

- **New project**: choose a name and the working folder (a folder dialog opens in the desktop app). `<working folder>/<name>.video-flow` is created and opened. Characters that file systems refuse are removed from the name, and an existing project of that name is refused.
- **Open project…**: choose a `.video-flow` folder. Only valid project folders are accepted; anything else is refused with an explanation.
- **Recent projects**: each line shows the name and its working folder, with four actions:
  - **Open**;
  - **Rename**: renames the project and its folder, in the same working folder;
  - **Remove from list**: forgets the project here, keeping its folder and media;
  - **Delete**: after a confirmation, moves the project folder to the system trash, where you can restore it. Your media are never touched.

## Opening, saving

- The desktop app reopens your most recent project at launch, or shows the home page when there is none. From a terminal, `videoflow desktop --project PATH` opens or creates a given project folder.
- Every change is saved at once. **Save** names an untitled project (and its folder). **Save as** (the arrow next to Save) copies the project as `<new name>.video-flow` in the same working folder and opens the copy. The window title shows the open project.

Projects made by earlier versions open as before; they are added to the recent list the first time.

## Technical notes

Folder contents, naming, validity and security rules: [projects, cache and FFmpeg](../../architecture/projects-and-setup.md). Tests: [validation record](../../validation/2026-11-12-manual-pages.md#projects).
