import { useEffect, useState } from "react";
import { Film, Plus, X } from "lucide-react";
import { api, useEditor, flushClipUpdates } from "../store";

interface Entry {
  id: string;
  name: string;
  path: string;
}
export function Home({ onClose }: { onClose: () => void }) {
  const { project, load, set } = useEditor();
  const [projects, setProjects] = useState<Entry[]>([]),
    [busy, setBusy] = useState(false),
    [action, setAction] = useState<{
      kind: "new" | "rename" | "delete";
      entry?: Entry;
    } | null>(null),
    [name, setName] = useState("");
  const refresh = () =>
    api<Entry[]>("/projects")
      .then(setProjects)
      .catch((e) => set({ error: String(e) }));
  useEffect(() => {
    void refresh();
  }, []);
  async function perform(kind: string, id?: string) {
    setBusy(true);
    try {
      await flushClipUpdates();
      await api("/projects/action", {
        method: "POST",
        body: JSON.stringify({ kind, id, name }),
      });
      if (kind === "open" || kind === "new") {
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
      } else {
        await load();
        await refresh();
      }
      setAction(null);
    } catch (e) {
      set({ error: String(e) });
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="home-page">
      <div className="home-heading">
        <div>
          <Film size={28} />
          <h1>Your projects</h1>
        </div>
        <button className="button" onClick={onClose}>
          <X size={16} />
          Back to editor
        </button>
      </div>
      <button
        className="primary"
        disabled={busy}
        onClick={() => {
          setName("Untitled");
          setAction({ kind: "new" });
        }}
      >
        <Plus size={16} />
        New project
      </button>
      <div className="project-list">
        {projects.map((entry) => (
          <article key={entry.id}>
            <div>
              <h2>{entry.name}</h2>
              {entry.id === project?.id && <small>Open project</small>}
            </div>
            <button
              className="button"
              disabled={busy}
              onClick={() => void perform("open", entry.id)}
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
              onClick={() => setAction({ kind: "delete", entry })}
            >
              Delete
            </button>
          </article>
        ))}
      </div>
      {action && (
        <div className="modal-backdrop">
          <form
            className="modal"
            role="dialog"
            aria-label={`${action.kind} project`}
            onSubmit={(e) => {
              e.preventDefault();
              void perform(action.kind, action.entry?.id);
            }}
          >
            <div className="modal-heading">
              <h2>
                {action.kind === "delete"
                  ? `Delete ${action.entry?.name}?`
                  : action.kind === "new"
                    ? "New project"
                    : "Rename project"}
              </h2>
              <button type="button" onClick={() => setAction(null)}>
                <X size={18} />
              </button>
            </div>
            {action.kind === "delete" ? (
              <p>
                The project bundle moves to the project trash folder. Original
                media remains in place.
              </p>
            ) : (
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
            <button
              className="primary"
              disabled={busy || (action.kind !== "delete" && !name.trim())}
            >
              {action.kind === "delete" ? "Delete project" : "Save"}
            </button>
          </form>
        </div>
      )}
    </div>
  );
}
