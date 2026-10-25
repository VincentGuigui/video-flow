import { useRef, useState } from "react";
import {
  FileVideo,
  X,
  Check,
  LoaderCircle,
  FolderOpen,
  ArrowRight,
  Square,
} from "lucide-react";
import { api, useEditor } from "../store";
import { type NativeFile } from "../desktop";

interface Job {
  id: string;
  filename: string;
  state: string;
  progress: number;
  phase: string;
  error: string | null;
  cached: boolean;
  warning: string | null;
  analysisPath: string | null;
  inverses: Record<string, unknown>[];
}
interface Item {
  name: string;
  progress: number;
  phase: string;
  state: string;
  id?: string;
}
const pause = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));
export function ImportDialog({
  selections,
  onClose,
}: {
  selections: NativeFile[];
  onClose: () => void;
}) {
  const { load, roots, set } = useEditor();
  const [analyse, setAnalyse] = useState(true),
    [path, setPath] = useState(""),
    [items, setItems] = useState<Item[]>([]),
    [running, setRunning] = useState(false),
    [finished, setFinished] = useState(false),
    [error, setError] = useState("");
  const stopped = useRef(false),
    skip = useRef(false),
    active = useRef<string | null>(null);
  function update(index: number, values: Partial<Item>) {
    setItems((old) =>
      old.map((item, i) => (i === index ? { ...item, ...values } : item)),
    );
  }
  async function run() {
    stopped.current = false;
    setRunning(true);
    setError("");
    const names = selections.length
      ? selections.map((f) => f.name)
      : [path.split(/[\\/]/).at(-1) ?? path];
    setItems(
      names.map((name) => ({
        name,
        state: "queued",
        progress: 0,
        phase: "Waiting",
      })),
    );
    try {
      for (let i = 0; i < names.length; i++) {
        if (stopped.current) break;
        skip.current = false;
        update(i, { state: "running", phase: "Referencing original file" });
        try {
          const job = selections.length
            ? await api<Job>("/native-import", {
                method: "POST",
                body: JSON.stringify({ handle: selections[i].handle, analyse }),
              })
            : await api<Job>("/import-path", {
                method: "POST",
                body: JSON.stringify({ path, analyse }),
              });
          active.current = job.id;
          if (stopped.current || skip.current)
            await api("/jobs/cancel?job_id=" + job.id, { method: "POST" });
          let current = job;
          while (!["done", "cancelled", "failed"].includes(current.state)) {
            await pause(350);
            const jobs = await api<Job[]>("/jobs");
            current = jobs.find((j) => j.id === job.id)!;
            update(i, {
              id: job.id,
              state: current.state,
              progress: current.progress,
              phase: current.phase,
            });
          }
          update(i, {
            state: current.state,
            progress: current.state === "done" ? 1 : current.progress,
            phase:
              current.error ??
              current.warning ??
              (current.cached
                ? "Ready · existing analysis reused"
                : current.phase),
          });
          if (current.state === "done") {
            await load();
            const state = useEditor.getState();
            if (current.inverses?.length)
              set({
                history: [...state.history, current.inverses],
                future: [],
              });
          }
        } catch (e) {
          update(i, {
            state: skip.current || stopped.current ? "cancelled" : "failed",
            phase: String(e),
          });
        }
        active.current = null;
      }
    } catch (e) {
      setError(String(e));
    } finally {
      setItems((old) =>
        old.map((c) =>
          c.state === "queued"
            ? { ...c, state: "cancelled", phase: "Cancelled" }
            : c,
        ),
      );
      setRunning(false);
      setFinished(true);
      await load();
    }
  }
  async function cancel(all: boolean) {
    if (all) stopped.current = true;
    else skip.current = true;
    if (active.current)
      await api("/jobs/cancel?job_id=" + active.current, { method: "POST" });
  }
  const complete = items.filter((i) =>
    ["done", "failed", "cancelled"].includes(i.state),
  ).length;
  return (
    <div className="modal-backdrop">
      <section
        className="modal import-modal"
        role="dialog"
        aria-modal="true"
        aria-label="Import clips"
      >
        <div className="modal-heading">
          <div>
            <span className="overline">BRING YOUR STORY IN</span>
            <h2>
              {running
                ? "Importing clips"
                : finished
                  ? "Import complete"
                  : "Add to your assembly"}
            </h2>
          </div>
          <button
            className="icon-button"
            aria-label="Close import"
            disabled={running}
            onClick={onClose}
          >
            <X size={20} />
          </button>
        </div>
        {!running && !finished ? (
          <>
            <p className="muted">
              {selections.length
                ? `${selections.length} original file${selections.length === 1 ? "" : "s"} selected. No media will be copied.`
                : "Import a local video or audio file using its full path."}
            </p>
            {!selections.length && (
              <label className="field-label">
                Local file path
                <input
                  autoFocus
                  placeholder="C:\Rushes\take-01.mp4"
                  value={path}
                  onChange={(e) => setPath(e.target.value)}
                />
                <small>
                  Diagnostic mode · allowed roots: {roots.join(", ")}
                </small>
              </label>
            )}
            <button
              className={`analysis-option ${analyse ? "chosen" : ""}`}
              onClick={() => setAnalyse(true)}
            >
              <span className="radio-dot" />
              <div>
                <strong>Analyse & group similar takes</strong>
                <p>
                  Reuse existing JSON, or transcribe and create a summary and
                  keywords. Matching clips become parallel choices.
                </p>
                <small>First analysis may download local speech models.</small>
              </div>
            </button>
            <button
              className={`analysis-option ${!analyse ? "chosen" : ""}`}
              onClick={() => setAnalyse(false)}
            >
              <span className="radio-dot" />
              <div>
                <strong>Import only</strong>
                <p>Add clips in sequence. Start editing immediately.</p>
              </div>
            </button>
            <div className="modal-footer">
              <span>
                <FolderOpen size={14} />
                Originals stay in place
              </span>
              <button
                className="primary"
                disabled={!selections.length && !path.trim()}
                onClick={() => void run()}
              >
                Import {selections.length || "clip"} <ArrowRight size={15} />
              </button>
            </div>
          </>
        ) : (
          <>
            <div className="global-progress">
              <span>
                {complete} / {items.length} files complete
              </span>
              <strong>
                {Math.round(
                  (items.reduce(
                    (sum, i) =>
                      sum +
                      (["done", "failed", "cancelled"].includes(i.state)
                        ? 1
                        : i.progress),
                    0,
                  ) /
                    Math.max(1, items.length)) *
                    100,
                )}
                %
              </strong>
            </div>
            <div className="progress-track">
              <i
                style={{
                  width: `${(items.reduce((sum, i) => sum + (["done", "failed", "cancelled"].includes(i.state) ? 1 : i.progress), 0) / Math.max(1, items.length)) * 100}%`,
                }}
              />
            </div>
            <div className="import-list">
              {items.map((item, i) => (
                <div className={`import-item ${item.state}`} key={i}>
                  <div className="file-icon">
                    {item.state === "done" ? (
                      <Check size={18} />
                    ) : item.state === "running" ? (
                      <LoaderCircle className="spin" size={18} />
                    ) : (
                      <FileVideo size={18} />
                    )}
                  </div>
                  <div className="import-item-body">
                    <strong>{item.name}</strong>
                    <small>{item.phase}</small>
                    {item.state === "running" && (
                      <div className="progress-track small">
                        <i style={{ width: `${item.progress * 100}%` }} />
                      </div>
                    )}
                  </div>
                  {item.state === "running" && (
                    <button
                      className="icon-button"
                      title="Cancel this file"
                      onClick={() => void cancel(false)}
                    >
                      <X size={15} />
                    </button>
                  )}
                </div>
              ))}
            </div>
            {error && <p className="error">{error}</p>}
            <div className="modal-footer">
              <span>
                {running
                  ? "Processing one file at a time."
                  : "Imported references are saved in your project."}
              </span>
              {running ? (
                <button className="button" onClick={() => void cancel(true)}>
                  <Square size={12} />
                  Cancel all
                </button>
              ) : (
                <button className="primary" onClick={onClose}>
                  Back to editor
                  <ArrowRight size={14} />
                </button>
              )}
            </div>
          </>
        )}
      </section>
    </div>
  );
}
