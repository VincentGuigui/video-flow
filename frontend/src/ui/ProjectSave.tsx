import { useState } from "react";
import { Save, ChevronDown, X } from "lucide-react";
import { api, useEditor } from "../store";

export function ProjectSave() {
  const { project, busy, set, load } = useEditor();
  const [menu, setMenu] = useState(false),
    [mode, setMode] = useState<"save" | "copy" | null>(null),
    [name, setName] = useState(""),
    [working, setWorking] = useState(false);
  function ask(copy: boolean) {
    setMenu(false);
    setName(
      copy
        ? `${project?.name ?? "Untitled"} copy`
        : (project?.name ?? "Untitled"),
    );
    setMode(copy ? "copy" : "save");
  }
  async function save(copy: boolean, value?: string) {
    setWorking(true);
    try {
      await api("/project/save", {
        method: "POST",
        body: JSON.stringify({
          name: value,
          copy,
          baseRevision: project?.revision,
        }),
      });
      if (copy)
        set({
          selected: null,
          focus: null,
          frame: 0,
          playing: false,
          history: [],
          future: [],
        });
      await load();
      setMode(null);
    } catch (e) {
      set({ error: String(e) });
    } finally {
      setWorking(false);
    }
  }
  return (
    <>
      <div className="save-split">
        <button
          className="button"
          disabled={busy || working}
          onClick={() =>
            project?.name.toLowerCase().startsWith("untitled")
              ? ask(false)
              : void save(false)
          }
        >
          <Save size={15} />
          Save
        </button>
        <button
          className="icon-button"
          aria-label="Save options"
          aria-expanded={menu}
          onClick={() => setMenu(!menu)}
        >
          <ChevronDown size={14} />
        </button>
        {menu && (
          <div className="save-menu">
            <button onClick={() => ask(true)}>Save as…</button>
          </div>
        )}
      </div>
      {mode && (
        <div className="modal-backdrop">
          <form
            className="modal"
            role="dialog"
            aria-label={mode === "copy" ? "Save as" : "Name project"}
            onSubmit={(e) => {
              e.preventDefault();
              void save(mode === "copy", name);
            }}
          >
            <div className="modal-heading">
              <h2>{mode === "copy" ? "Save as…" : "Save project"}</h2>
              <button
                type="button"
                aria-label="Close save"
                onClick={() => setMode(null)}
              >
                <X size={18} />
              </button>
            </div>
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
            <p className="muted">
              {mode === "copy"
                ? "Copies the edit and analysis. Original media stays in place."
                : "Changes are also saved automatically as you edit."}
            </p>
            <button className="primary" disabled={working || !name.trim()}>
              Save
            </button>
          </form>
        </div>
      )}
    </>
  );
}
