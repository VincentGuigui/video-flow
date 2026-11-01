import { useEffect, useState } from "react";
import { Film, FolderOpen, Plus, X } from "lucide-react";
import { api, useEditor, flushClipUpdates } from "../store";
import { native, type NativeFolder } from "../desktop";

interface Entry {
  id: string;
  name: string;
  path: string;
  folder: string;
}
type Action =
  | { kind: "new" }
  | { kind: "open" }
  | { kind: "rename"; entry: Entry }
  | { kind: "delete"; entry: Entry };

// Recent projects. A project is a `<name>.video-flow` folder inside a working folder;
// in the desktop app folders are chosen natively, in a browser they are typed.
export function Home({ onClose }: { onClose: () => void }) {
  const { load, set } = useEditor();
  const [projects, setProjects] = useState<Entry[]>([]),
    [busy, setBusy] = useState(false),
    [action, setAction] = useState<Action | null>(null),
    [name, setName] = useState(""),
    [folder, setFolder] = useState<NativeFolder | null>(null),
    [path, setPath] = useState("");
  const refresh = () =>
    api<Entry[]>("/projects")
      .then(setProjects)
      .catch((e) => set({ error: String(e) }));
  useEffect(() => {
    void refresh();
    const chosen = (event: Event) => {
      const detail = (event as CustomEvent<NativeFolder>).detail;
      if (detail.purpose === "project")
        void perform({ kind: "open", folder: detail.handle });
      else setFolder(detail);
    };
    window.addEventListener("videoflow-folder", chosen);
    return () => window.removeEventListener("videoflow-folder", chosen);
  }, []);
  async function perform(body: Record<string, unknown>) {
    setBusy(true);
    try {
      await flushClipUpdates();
      await api("/projects/action", {
        method: "POST",
        body: JSON.stringify(body),
      });
      if (body.kind === "open" || body.kind === "new") {
        set({
          selected: null,
          focus: null,
          frame: 0,
          playing: false,
          history: [],
          future: [],
        });
        await load();
        onClose();
      } else await refresh(); // the closed project stays closed
      setAction(null);
    } catch (e) {
      set({ error: String(e) });
    } finally {
      setBusy(false);
    }
  }
  function submit() {
    if (!action) return;
    if (action.kind === "rename")
      void perform({ kind: "rename", id: action.entry.id, name });
    else if (action.kind === "delete")
      void perform({ kind: "delete", id: action.entry.id });
    else if (action.kind === "new")
      void perform({
        kind: "new",
        name,
        ...(native() ? { folder: folder?.handle } : { path }),
      });
    else void perform({ kind: "open", path });
  }
  const ready =
    action?.kind === "delete"
      ? true
      : action?.kind === "rename"
        ? !!name.trim()
        : action?.kind === "new"
          ? !!name.trim() && (native() ? !!folder : !!path.trim())
          : !!path.trim();
  return (
    <div className="home-page">
      <div className="home-heading">
        <div>
          <Film size={28} />
          <h1>Your projects</h1>
        </div>
      </div>
      <div className="home-actions">
        <button
          className="primary"
          disabled={busy}
          onClick={() => {
            setName("Untitled");
            setFolder(null);
            setPath("");
            setAction({ kind: "new" });
          }}
        >
          <Plus size={16} />
          New project
        </button>
        <button
          className="button"
          disabled={busy}
          title="Open a <name>.video-flow project folder"
          onClick={() => {
            if (native()) window.videoFlowDesktop?.pickFolder("project");
            else {
              setPath("");
              setAction({ kind: "open" });
            }
          }}
        >
          <FolderOpen size={16} />
          Open project…
        </button>
      </div>
      <div className="project-list">
        {projects.map((entry) => (
          <article key={entry.id}>
            <div>
              <h2>{entry.name}</h2>
              <small title={entry.path}>{entry.folder}</small>
            </div>
            <button
              className="button"
              disabled={busy}
              onClick={() => void perform({ kind: "open", id: entry.id })}
            >
              Open
            </button>
            <button
              className="button"
              disabled={busy}
              onClick={() => {
                setName(entry.name);
                setAction({ kind: "rename", entry });
              }}
            >
              Rename
            </button>
            <button
              className="button"
              disabled={busy}
              title="Forget this project here; its folder and media are kept"
              onClick={() => void perform({ kind: "remove", id: entry.id })}
            >
              Remove from list
            </button>
            <button
              className="button"
              disabled={busy}
              title="Move the project folder to the trash; media are kept"
              onClick={() => setAction({ kind: "delete", entry })}
            >
              Delete
            </button>
          </article>
        ))}
        {!projects.length && (
          <p className="muted">
            No recent project. Create one in the folder that holds your media,
            or open an existing project folder.
          </p>
        )}
      </div>
      {action && (
        <div className="modal-backdrop">
          <form
            className="modal"
            role="dialog"
            aria-label={`${action.kind} project`}
            onSubmit={(e) => {
              e.preventDefault();
              submit();
            }}
          >
            <div className="modal-heading">
              <h2>
                {action.kind === "new"
                  ? "New project"
                  : action.kind === "open"
                    ? "Open project"
                    : action.kind === "delete"
                      ? `Delete ${action.entry.name}?`
                      : "Rename project"}
              </h2>
              <button type="button" onClick={() => setAction(null)}>
                <X size={18} />
              </button>
            </div>
            {action.kind === "delete" && (
              <p>
                The project folder{" "}
                <code>{action.entry.path.split(/[\\/]/).at(-1)}</code> moves to
                the trash, where it can be restored. The media in{" "}
                <code>{action.entry.folder}</code> are not touched.
              </p>
            )}
            {(action.kind === "new" || action.kind === "rename") && (
              <label>
                Project name
                <input
                  autoFocus
                  required
                  maxLength={120}
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                />
              </label>
            )}
            {action.kind === "new" && native() && (
              <div className="folder-choice">
                <span>Working folder (with your media)</span>
                <button
                  type="button"
                  className="button"
                  onClick={() => window.videoFlowDesktop?.pickFolder("workdir")}
                >
                  <FolderOpen size={15} />
                  {folder ? folder.path : "Choose folder…"}
                </button>
              </div>
            )}
            {(action.kind === "new" || action.kind === "open") && !native() && (
              <label>
                {action.kind === "new"
                  ? "Working folder (with your media)"
                  : "Project folder (.video-flow)"}
                <input
                  required
                  value={path}
                  onChange={(e) => setPath(e.target.value)}
                  placeholder="/path/to/folder"
                />
              </label>
            )}
            {action.kind === "new" && (
              <p className="muted">
                The project is saved as{" "}
                <code>{(name.trim() || "Untitled") + ".video-flow"}</code> in
                this folder. Media are referenced relative to it, so the whole
                folder can be moved or copied.
              </p>
            )}
            <button className="primary" disabled={busy || !ready}>
              {action.kind === "open"
                ? "Open"
                : action.kind === "new"
                  ? "Create project"
                  : action.kind === "delete"
                    ? "Move to trash"
                    : "Save"}
            </button>
          </form>
        </div>
      )}
    </div>
  );
}
