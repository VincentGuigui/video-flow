import { useEffect, useState } from "react";
import { Cpu, Film, X } from "lucide-react";
import { api, useEditor } from "../store";
import { CacheSettings } from "./CacheSettings";
import { ManageModels } from "./ManageModels";
import { FfmpegSetup } from "./FfmpegSetup";

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
  size: number | null;
  disk: number;
  name: string;
  purpose: string;
  goal?: string;
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
export function Settings({ onClose }: { onClose: () => void }) {
  const [data, setData] = useState<SettingsData | null>(null),
    [preferences, setPreferences] = useState<Preferences | null>(null),
    [saving, setSaving] = useState(false),
    [message, setMessage] = useState(""),
    [models, setModels] = useState(false),
    [ffmpeg, setFfmpeg] = useState(false);
  const { set } = useEditor();
  useEffect(() => {
    let stopped = false;
    const poll = async () => {
      try {
        const result = await api<SettingsData>("/settings");
        if (!stopped) {
          // Polling must not re-render an unchanged dialog.
          setData((old) =>
            JSON.stringify(old) === JSON.stringify(result) ? old : result,
          );
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
            <h3>Cache</h3>
            <CacheSettings />
            <h3>AI models</h3>
            <div className="settings-cache">
              <p className="muted">
                Download, update or remove the local models used for
                transcription, grouping and summaries.
              </p>
              <div className="cache-actions">
                <button className="button" onClick={() => setModels(true)}>
                  <Cpu size={15} />
                  Manage AI models…
                </button>
              </div>
            </div>
            <h3>FFmpeg</h3>
            <div className="settings-cache">
              <p className="muted">
                The media tool used to read, preview and render video. Check its
                version or install it.
              </p>
              <div className="cache-actions">
                <button className="button" onClick={() => setFfmpeg(true)}>
                  <Film size={15} />
                  FFmpeg…
                </button>
              </div>
            </div>
          </>
        )}
      </section>
      {models && <ManageModels onClose={() => setModels(false)} />}
      {ffmpeg && <FfmpegSetup onClose={() => setFfmpeg(false)} />}
    </div>
  );
}
