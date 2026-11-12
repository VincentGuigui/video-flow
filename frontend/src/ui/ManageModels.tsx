import { useEffect, useState } from "react";
import { Download, Trash2, X } from "lucide-react";
import { api, useEditor } from "../store";
import { formatSize } from "./CacheSettings";
import type { SettingsData } from "./Settings";
import { RuntimeSetup } from "./RuntimeSetup";

type Model = SettingsData["models"][number];

// Pinned AI models: what each one does, its download size and disk usage, and download,
// update, cancel and remove actions. Shown from Settings, at first start and when an
// import needs a missing model.
export function ManageModels({
  onClose,
  requested = false,
}: {
  onClose: () => void;
  requested?: boolean;
}) {
  const { set } = useEditor();
  const [data, setData] = useState<SettingsData | null>(null),
    [removing, setRemoving] = useState<string | null>(null);
  useEffect(() => {
    let stopped = false;
    const poll = async () => {
      try {
        const result = await api<SettingsData>("/settings");
        if (!stopped)
          // Polling must not re-render an unchanged dialog.
          setData((old) =>
            JSON.stringify(old) === JSON.stringify(result) ? old : result,
          );
      } catch (e) {
        if (!stopped) set({ error: String(e) });
      }
    };
    void poll();
    // Download sizes come from the Hub metadata once, then from the local cache.
    void api("/models/sizes", { method: "POST" })
      .then(() => poll())
      .catch(() => undefined);
    const timer = setInterval(() => void poll(), 750);
    return () => {
      stopped = true;
      clearInterval(timer);
    };
  }, [set]);
  async function download(id: string) {
    try {
      await api(`/models/${id}/download`, { method: "POST" });
    } catch (e) {
      set({ error: String(e) });
    }
  }
  async function remove(model: Model) {
    setRemoving(model.id);
    try {
      setData(
        await api<SettingsData>(`/models/${model.id}/remove`, {
          method: "POST",
        }),
      );
    } catch (e) {
      set({ error: String(e) });
    } finally {
      setRemoving(null);
    }
  }
  const models =
    data?.models.filter(
      (m) =>
        m.purpose !== "summary" || data.preferences.summaryEngine === "qwen",
    ) ?? [];
  const missing = models.filter((m) => m.required && m.state !== "up-to-date");
  // A total only when every size is known (sizes come from the Hub, never guessed).
  const missingSize = missing.every((m) => m.size != null)
    ? missing.reduce((sum, m) => sum + (m.size ?? 0), 0)
    : null;
  return (
    <div className="modal-backdrop settings-backdrop">
      <section
        className="modal settings-panel"
        role="dialog"
        aria-modal="true"
        aria-label="Manage AI models"
      >
        <div className="modal-heading">
          <h2>{requested ? "Install components" : "Manage AI models"}</h2>
          <button aria-label="Close AI models" onClick={onClose}>
            <X size={20} />
          </button>
        </div>
        {requested && (
          <p className="settings-notice">
            Local analysis needs runtime dependencies and model files. Install
            them below, or close this window to continue editing without
            analysis. Downloads only start when you ask.
          </p>
        )}
        <RuntimeSetup />
        <h3>AI model files</h3>
        <p className="muted">
          Models folder: <code>{data?.directory}</code>
        </p>
        {missing.length > 0 && (
          <div className="settings-notice">
            <p>
              {missing.length} required model
              {missing.length === 1 ? " is" : "s are"} missing or obsolete
              {missingSize != null
                ? ` (${formatSize(missingSize)} to download).`
                : "."}
            </p>
            <button
              className="button"
              onClick={() => {
                for (const model of missing) void download(model.id);
              }}
            >
              <Download size={15} />
              Download required models
            </button>
          </div>
        )}
        <div className="model-list">
          {models.map((model) => {
            const active =
              model.download &&
              ["queued", "running"].includes(model.download.state);
            return (
              <article key={model.id}>
                <div>
                  <strong>{model.name}</strong>
                  {model.goal && <p className="model-goal">{model.goal}</p>}
                  <p className="muted">
                    {model.purpose} · {model.license}
                    {model.required ? " · required" : " · optional"}
                  </p>
                  <p className="muted model-sizes">
                    Download{" "}
                    {model.size ? formatSize(model.size) : "size unknown"}
                    {" · "}On disk{" "}
                    {model.disk ? formatSize(model.disk) : "nothing"}
                  </p>
                  <span
                    className={`model-state ${model.state}`}
                    title={
                      model.state === "obsolete"
                        ? "This app supports a newer version. Update downloads it."
                        : undefined
                    }
                  >
                    {model.state === "up-to-date"
                      ? "Up to date"
                      : model.state === "obsolete"
                        ? "Obsolete"
                        : "Missing"}
                  </span>
                  {model.runtimeMissing.length > 0 && (
                    <p className="error">
                      Runtime components missing:{" "}
                      {model.runtimeMissing.join(", ")}. Use Runtime components
                      above to install or repair them.
                    </p>
                  )}
                  {active && (
                    <>
                      <p>{model.download?.phase}</p>
                      <progress max={1} value={model.download?.progress} />
                    </>
                  )}
                  {model.download?.error && (
                    <p className="error">{model.download.error}</p>
                  )}
                </div>
                <div className="model-actions">
                  {active ? (
                    <button
                      className="button"
                      onClick={() =>
                        void api(`/models/${model.id}/cancel`, {
                          method: "POST",
                        }).catch((e) => set({ error: String(e) }))
                      }
                    >
                      Cancel
                    </button>
                  ) : (
                    <button
                      className="button"
                      disabled={model.state === "up-to-date"}
                      onClick={() => void download(model.id)}
                    >
                      {model.state === "up-to-date"
                        ? "Already downloaded"
                        : model.state === "obsolete"
                          ? "Update"
                          : "Download"}
                    </button>
                  )}
                  <button
                    className="button"
                    disabled={!!active || !model.disk || removing !== null}
                    title="Delete this model's files; it can be downloaded again"
                    onClick={() => void remove(model)}
                  >
                    <Trash2 size={14} />
                    Remove
                  </button>
                </div>
              </article>
            );
          })}
        </div>
      </section>
    </div>
  );
}
