import { useEffect, useState } from "react";
import { api, useEditor } from "../store";
import type { SettingsData } from "./Settings";

export interface ComponentState {
  components: {
    id: string;
    name: string;
    available: boolean;
    optional: boolean;
    missing: string[];
    detail: string;
    installable: boolean;
  }[];
  packaged: boolean;
  job: null | {
    component: string;
    state: string;
    phase: string;
    error: string | null;
    restartRequired: boolean;
  };
}

export function RuntimeSetup() {
  const [data, setData] = useState<ComponentState | null>(null);
  const [error, setError] = useState("");
  const { set } = useEditor();
  useEffect(() => {
    let stopped = false;
    const poll = async () => {
      try {
        const result = await api<ComponentState>("/components");
        if (!stopped)
          setData((old) =>
            JSON.stringify(old) === JSON.stringify(result) ? old : result,
          );
      } catch (e) {
        if (!stopped) setError(String(e));
      }
    };
    void poll();
    const timer = setInterval(() => void poll(), 1000);
    return () => {
      stopped = true;
      clearInterval(timer);
    };
  }, []);
  const running = data?.job?.state === "running";
  async function install(id: string) {
    setError("");
    try {
      await api(`/components/${id}/install`, { method: "POST" });
      setData(await api<ComponentState>("/components"));
    } catch (e) {
      setError(String(e));
    }
  }
  async function useCpu() {
    try {
      const current = await api<SettingsData>("/settings");
      await api("/settings", {
        method: "PUT",
        body: JSON.stringify({ ...current.preferences, aiDevice: "cpu" }),
      });
      setData(await api<ComponentState>("/components"));
      set({ error: "" });
    } catch (e) {
      setError(String(e));
    }
  }
  return (
    <section aria-label="Runtime components">
      <h3>Runtime components</h3>
      <p className="muted">
        Dependencies run the AI models. Model files are downloaded separately
        below. Installation starts only when you ask.
      </p>
      {!data && !error && <p>Checking dependencies and acceleration…</p>}
      {data?.components.map((component) => (
        <article className="settings-notice" key={component.id}>
          <strong>
            {component.name} ·{" "}
            {component.available
              ? "Ready"
              : component.optional
                ? "Unavailable"
                : "Missing"}
          </strong>
          {component.optional && <span> · optional</span>}
          {!component.available && (
            <>
              <p>{component.detail}</p>
              {component.installable ? (
                <button
                  className="button"
                  disabled={running || data.job?.restartRequired}
                  onClick={() => void install(component.id)}
                >
                  Install{" "}
                  {component.id === "cuda" ? "CUDA libraries" : "dependencies"}
                </button>
              ) : (
                <p>
                  {data.packaged
                    ? component.id === "cuda"
                      ? "Use a complete CUDA release and a compatible NVIDIA driver, or choose CPU."
                      : "Reinstall a complete Video-Flow release to repair bundled dependencies."
                    : "Run the Video-Flow installer to restore these components."}
                </p>
              )}
              {component.id === "cuda" && (
                <>
                  <button
                    className="button"
                    disabled={running}
                    onClick={() => void useCpu()}
                  >
                    Use CPU
                  </button>
                  <p className="muted">
                    A supported NVIDIA driver is also required. Windows needs
                    the Microsoft Visual C++ runtime. Restart after
                    installation; if CUDA still cannot initialize, analysis can
                    use the CPU.
                  </p>
                </>
              )}
            </>
          )}
        </article>
      ))}
      {data?.job && <p role="status">{data.job.phase}</p>}
      {running && (
        <button
          className="button"
          onClick={() =>
            void api("/components/cancel", { method: "POST" }).catch((e) =>
              setError(String(e)),
            )
          }
        >
          Cancel installation
        </button>
      )}
      {(error || data?.job?.error) && (
        <p className="error">{error || data?.job?.error}</p>
      )}
    </section>
  );
}
