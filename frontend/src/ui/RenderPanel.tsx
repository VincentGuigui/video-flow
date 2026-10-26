import { useEffect, useState } from "react";
import { Download } from "lucide-react";
import type { SettingsData } from "./Settings";
import { api, useEditor } from "../store";

interface Job {
  id: string;
  revision: number;
  state: string;
  phase: string;
  progress: number;
  path: string | null;
  error: string | null;
}
export function RenderPanel() {
  const { project, busy, set } = useEditor();
  const [jobs, setJobs] = useState<Job[]>([]),
    [working, setWorking] = useState(false),
    [preset, setPreset] = useState("final"),
    [normalize, setNormalize] = useState(true);
  useEffect(() => {
    void api<SettingsData>("/settings")
      .then((data) => {
        setPreset(data.preferences.renderPreset);
        setNormalize(data.preferences.normalizeAudio);
      })
      .catch((e) => set({ error: String(e) }));
    let stopped = false;
    async function poll() {
      try {
        const result = await api<Job[]>("/renders");
        if (!stopped) setJobs(result);
      } catch (e) {
        if (!stopped) set({ error: String(e) });
      }
    }
    void poll();
    const timer = setInterval(() => void poll(), 500);
    return () => {
      stopped = true;
      clearInterval(timer);
    };
  }, [set]);
  const job = jobs.at(-1),
    active = jobs.some((j) => j.state === "queued" || j.state === "running");
  async function start() {
    setWorking(true);
    try {
      const next = await api<Job>("/render", {
        method: "POST",
        body: JSON.stringify({
          baseRevision: project?.revision,
          preset,
          normalize,
        }),
      });
      setJobs([...jobs, next]);
    } catch (e) {
      set({ error: String(e) });
    } finally {
      setWorking(false);
    }
  }
  return (
    <section className="render-panel">
      <button
        className="export-option"
        disabled={busy || working || active}
        onClick={() => void start()}
      >
        <Download size={19} />
        <div>
          <strong>Save as MP4 video</strong>
          <p>Render enabled clips, layers and audio into a video.</p>
        </div>
      </button>
      <div className="render-options">
        <select
          aria-label="Render quality"
          value={preset}
          onChange={(e) => setPreset(e.target.value)}
          disabled={active}
        >
          <option value="final">Full resolution</option>
          <option value="draft">Draft preview</option>
        </select>
        <label>
          <input
            type="checkbox"
            checked={normalize}
            disabled={active}
            onChange={(e) => setNormalize(e.target.checked)}
          />
          Normalize audio
        </label>
      </div>
      {job && (
        <div className="output-result" role="status">
          <span>
            {job.error ?? job.phase} · revision {job.revision}
          </span>
          {active && (
            <>
              <progress max={1} value={job.progress} />
              <button
                className="button"
                onClick={() =>
                  void api(`/renders/${job.id}/cancel`, {
                    method: "POST",
                  }).catch((e) => set({ error: String(e) }))
                }
              >
                Cancel render
              </button>
            </>
          )}
          {job.path && (
            <>
              <p>{job.path}</p>
              {window.videoFlowDesktop ? (
                <button
                  className="button"
                  onClick={() =>
                    window.videoFlowDesktop?.saveRenderedVideo(job.id)
                  }
                >
                  Save video as…
                </button>
              ) : (
                <a href={`/api/renders/${job.id}/file`} download>
                  Download MP4
                </a>
              )}
            </>
          )}
        </div>
      )}
    </section>
  );
}
