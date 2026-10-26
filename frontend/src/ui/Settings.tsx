import { useEffect, useState } from "react";
import { Download, X } from "lucide-react";
import { api, useEditor } from "../store";

export interface Preferences {
  summaryEngine: "deterministic" | "qwen";
  asrEngine: "parakeet" | "faster-whisper";
  aiDevice: "auto" | "cpu" | "gpu" | "npu";
  analyseImports: boolean;
  renderPreset: "draft" | "final";
  normalizeAudio: boolean;
}
interface Model {
  id: string;
  name: string;
  purpose: string;
  state: string;
  required: boolean;
  revision: string;
  license: string;
  runtimeMissing: string[];
  download: null | {
    state: string;
    progress: number;
    phase: string;
    error: string | null;
  };
}
export interface SettingsData {
  preferences: Preferences;
  directory: string;
  models: Model[];
}
export function Settings({
  onClose,
  requested = false,
}: {
  onClose: () => void;
  requested?: boolean;
}) {
  const [data, setData] = useState<SettingsData | null>(null),
    [preferences, setPreferences] = useState<Preferences | null>(null),
    [saving, setSaving] = useState(false),
    [message, setMessage] = useState("");
  const { set } = useEditor();
  useEffect(() => {
    let stopped = false;
    const poll = async () => {
      try {
        const result = await api<SettingsData>("/settings");
        if (!stopped) {
          setData(result);
          setPreferences((old) => old ?? result.preferences);
        }
      } catch (e) {
        if (!stopped) set({ error: String(e) });
      }
    };
    void poll();
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
  async function save() {
    if (!preferences) return;
    setSaving(true);
    try {
      const result = await api<SettingsData>("/settings", {
        method: "PUT",
        body: JSON.stringify(preferences),
      });
      setData(result);
      setMessage("Settings saved.");
    } catch (e) {
      set({ error: String(e) });
    } finally {
      setSaving(false);
    }
  }
  const models =
    data?.models.filter(
      (m) => m.purpose !== "summary" || preferences?.summaryEngine === "qwen",
    ) ?? [];
  const required = (m: Model) =>
    m.id === "silero-vad" ||
    m.id ===
      (preferences?.asrEngine === "faster-whisper"
        ? "faster-whisper-tiny"
        : "parakeet-tdt-0.6b-v3-int8") ||
    (m.id === "qwen2.5-0.5b-instruct" && preferences?.summaryEngine === "qwen");
  const missing = models.filter((m) => required(m) && m.state !== "up-to-date");
  return (
    <div className="modal-backdrop settings-backdrop">
      <section
        className="modal settings-panel"
        role="dialog"
        aria-modal="true"
        aria-label="Settings"
      >
        <div className="modal-heading">
          <h2>Settings</h2>
          <button aria-label="Close settings" onClick={onClose}>
            <X size={20} />
          </button>
        </div>
        {requested && (
          <p className="settings-notice">
            Local analysis needs model files. Download them below, or close
            Settings to continue editing without analysis. Downloads only start
            when you ask.
          </p>
        )}
        {preferences && (
          <>
            <div className="settings-grid">
              <label>
                Summary & keywords
                <select
                  aria-label="Summary engine"
                  value={preferences.summaryEngine}
                  onChange={(e) =>
                    setPreferences({
                      ...preferences,
                      summaryEngine: e.target
                        .value as Preferences["summaryEngine"],
                    })
                  }
                >
                  <option value="deterministic">
                    Deterministic · no model needed
                  </option>
                  <option value="qwen">Qwen · local CPU model</option>
                </select>
              </label>
              <label>
                Transcription
                <select
                  aria-label="Transcription engine"
                  value={preferences.asrEngine}
                  onChange={(e) =>
                    setPreferences({
                      ...preferences,
                      asrEngine: e.target.value as Preferences["asrEngine"],
                    })
                  }
                >
                  <option value="parakeet">Parakeet TDT 0.6B v3</option>
                  <option value="faster-whisper">
                    Whisper tiny · CPU/CUDA
                  </option>
                </select>
              </label>
              <label>
                Speech inference device
                <select
                  aria-label="Inference device"
                  value={preferences.aiDevice}
                  onChange={(e) =>
                    setPreferences({
                      ...preferences,
                      aiDevice: e.target.value as Preferences["aiDevice"],
                    })
                  }
                >
                  <option value="auto">Automatic · NPU / GPU / CPU</option>
                  <option value="cpu">CPU</option>
                  <option value="gpu">GPU preferred</option>
                  <option value="npu">NPU preferred</option>
                </select>
              </label>
              <label>
                Default video export
                <select
                  value={preferences.renderPreset}
                  onChange={(e) =>
                    setPreferences({
                      ...preferences,
                      renderPreset: e.target
                        .value as Preferences["renderPreset"],
                    })
                  }
                >
                  <option value="final">Full resolution</option>
                  <option value="draft">Draft preview</option>
                </select>
              </label>
              <label className="checkbox-label">
                <input
                  type="checkbox"
                  checked={preferences.analyseImports}
                  onChange={(e) =>
                    setPreferences({
                      ...preferences,
                      analyseImports: e.target.checked,
                    })
                  }
                />
                Analyse new imports by default
              </label>
              <label className="checkbox-label">
                <input
                  type="checkbox"
                  checked={preferences.normalizeAudio}
                  onChange={(e) =>
                    setPreferences({
                      ...preferences,
                      normalizeAudio: e.target.checked,
                    })
                  }
                />
                Normalize exported audio by default
              </label>
            </div>
            <div className="settings-save">
              <button
                className="primary"
                disabled={saving}
                onClick={() => void save()}
              >
                Save settings
              </button>
              <span role="status">{message}</span>
            </div>
            <h3>AI models</h3>
            <p className="muted">{data?.directory}</p>
            {missing.length > 0 && (
              <div className="settings-notice">
                <p>
                  {missing.length} required model
                  {missing.length === 1 ? " is" : "s are"} missing or obsolete.
                  Download now?
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
            <p className="muted">
              Status compares local files with the pinned versions supported by
              this app. Updates download those versions. No model files are
              stored in AppData.
            </p>
            <div className="model-list">
              {models.map((model) => {
                const active =
                  model.download &&
                  ["queued", "running"].includes(model.download.state);
                return (
                  <article key={model.id}>
                    <div>
                      <strong>{model.name}</strong>
                      <p>
                        {model.purpose} · {model.license}
                        {required(model) ? " · selected" : " · optional"}
                      </p>
                      <span className={`model-state ${model.state}`}>
                        {model.state === "up-to-date"
                          ? "Up to date"
                          : model.state === "obsolete"
                            ? "Obsolete"
                            : "Missing"}
                      </span>
                      {model.runtimeMissing.length > 0 && (
                        <p className="error">
                          Runtime components missing:{" "}
                          {model.runtimeMissing.join(", ")}. Install the
                          matching application inference extra.
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
                        onClick={() => void download(model.id)}
                      >
                        {model.state === "missing" ? "Download" : "Update"}
                      </button>
                    )}
                  </article>
                );
              })}
            </div>
          </>
        )}
      </section>
    </div>
  );
}
