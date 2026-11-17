// A newer Video-Flow on GitHub: shown at start before the FFmpeg and model windows, and
// from Settings (docs/features/getting-started/updates.md).
import { Download, RotateCw, X } from "lucide-react";
import { api, useEditor } from "../store";
import { native } from "../desktop";
import { formatSize } from "./CacheSettings";
import { useUpdate, type UpdateState } from "../updates";

export function UpdateDialog() {
  const { set } = useEditor();
  const { state: data, set: setUpdate } = useUpdate();
  const close = () => setUpdate({ open: false });
  const running = data?.job?.state === "running";
  const ready = data?.job?.state === "ready";
  const post = (path: string) =>
    api<UpdateState>(path, { method: "POST" })
      .then((state) => setUpdate({ state }))
      .catch((e) => set({ error: String(e) }));
  async function restart() {
    try {
      await api("/update/restart", { method: "POST" });
      window.videoFlowDesktop?.quit?.();
    } catch (e) {
      set({ error: String(e) });
    }
  }
  const release = data?.release;
  if (!data || !release) return null;
  return (
    <div className="modal-backdrop settings-backdrop">
      <section
        className="modal settings-panel update-dialog"
        role="dialog"
        aria-modal="true"
        aria-label="Update"
      >
        <div className="modal-heading">
          <h2>Video-Flow {release.version} is available</h2>
          <button aria-label="Close update" onClick={close}>
            <X size={20} />
          </button>
        </div>
        <p className="muted">
          You have version {data.current}.{" "}
          <a href={release.page}>Release notes on GitHub</a>
          {release.size > 0 && <> · download {formatSize(release.size)}</>}
        </p>
        {release.notes.length > 0 && (
          <>
            <h3>What's new</h3>
            <ul className="update-notes">
              {release.notes.map((note) => (
                <li key={note}>{note}</li>
              ))}
            </ul>
          </>
        )}
        {data.installable && native() ? (
          <p className="muted">
            The update is downloaded from GitHub and checked against its
            SHA-256; you can keep working while it downloads. Video-Flow then
            restarts in the new version; your projects, models, FFmpeg and
            settings are kept.
          </p>
        ) : (
          <p className="settings-notice">
            {data.reason ?? "This window cannot install the update"}. Download
            it from <code>{release.page}</code>.
          </p>
        )}
        {running && (
          <>
            <p>{data.job?.phase}</p>
            <progress max={1} value={data.job?.progress} />
          </>
        )}
        {data.job?.state === "failed" && (
          <p className="error">{data.job.error}</p>
        )}
        <div className="cache-actions">
          {ready ? (
            <button className="primary" onClick={() => void restart()}>
              <RotateCw size={15} />
              Restart and update
            </button>
          ) : running ? (
            <button
              className="button"
              onClick={() => void post("/update/cancel")}
            >
              Cancel
            </button>
          ) : (
            data.installable &&
            native() && (
              <button
                className="primary"
                onClick={() => void post("/update/install")}
              >
                <Download size={15} />
                Update now
              </button>
            )
          )}
          <button className="button" onClick={close}>
            {running ? "Continue in the background" : "Later"}
          </button>
          {!ready && !data.skipped && (
            <button
              className="text-button"
              disabled={running}
              onClick={() => void post("/update/skip").then(close)}
            >
              Skip this version
            </button>
          )}
        </div>
      </section>
    </div>
  );
}
