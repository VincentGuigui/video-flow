import { useEffect, useState } from "react";
import { Download, X } from "lucide-react";
import { api, useEditor } from "../store";
import { formatSize } from "./CacheSettings";

export interface FfmpegState {
  available: boolean;
  version: string | null;
  path: string | null;
  minimum: string;
  build: null | {
    platform: string;
    version: string;
    url: string;
    sha256: string;
    size: number;
    license: string;
    distributor: string;
  };
  target: string;
  job: null | {
    state: "running" | "done" | "cancelled" | "failed";
    progress: number;
    phase: string;
    error: string | null;
  };
}

// FFmpeg status and, with the user's consent, the download of the pinned build into
// tools/ffmpeg. Shown at start when no usable FFmpeg is found, and from Settings.
export function FfmpegSetup({
  onClose,
  requested = false,
}: {
  onClose: () => void;
  requested?: boolean;
}) {
  const { set } = useEditor();
  const [data, setData] = useState<FfmpegState | null>(null);
  const running = data?.job?.state === "running";
  useEffect(() => {
    let stopped = false;
    const poll = async () => {
      try {
        const result = await api<FfmpegState>("/ffmpeg");
        if (!stopped)
          setData((old) =>
            JSON.stringify(old) === JSON.stringify(result) ? old : result,
          );
      } catch (e) {
        if (!stopped) set({ error: String(e) });
      }
    };
    void poll();
    // Poll only while a download runs.
    const timer = running ? setInterval(() => void poll(), 750) : undefined;
    return () => {
      stopped = true;
      clearInterval(timer);
    };
  }, [set, running]);
  async function install() {
    try {
      setData(await api<FfmpegState>("/ffmpeg/install", { method: "POST" }));
      setData(await api<FfmpegState>("/ffmpeg"));
    } catch (e) {
      set({ error: String(e) });
    }
  }
  const build = data?.build;
  const job = data?.job;
  return (
    <div className="modal-backdrop settings-backdrop">
      <section
        className="modal settings-panel"
        role="dialog"
        aria-modal="true"
        aria-label="FFmpeg"
      >
        <div className="modal-heading">
          <h2>FFmpeg</h2>
          <button aria-label="Close FFmpeg" onClick={onClose}>
            <X size={20} />
          </button>
        </div>
        {!data ? (
          <p className="muted">Looking for FFmpeg…</p>
        ) : data.available ? (
          <>
            <p>
              FFmpeg {data.version} is ready
              {job?.state === "done" ? ": it was installed." : "."}
            </p>
            <p className="muted">
              <code>{data.path}</code>
            </p>
            {requested && (
              <button className="primary" onClick={onClose}>
                Continue
              </button>
            )}
          </>
        ) : (
          <>
            <p className="settings-notice">
              Video-Flow needs FFmpeg {data.minimum} or newer to read media,
              make previews and render.{" "}
              {data.version
                ? `The FFmpeg found (${data.version}) is too old.`
                : "No FFmpeg was found."}
            </p>
            {build ? (
              <>
                <p>
                  Video-Flow can download FFmpeg {build.version} into{" "}
                  <code>{data.target}</code>. Nothing is downloaded until you
                  ask.
                </p>
                <ul className="ffmpeg-facts">
                  <li>
                    Built and distributed by {build.distributor}, who provides
                    its source code.
                  </li>
                  <li>
                    Licence {build.license}. FFmpeg is a separate program: it is
                    installed unchanged, with its licence files, and Video-Flow
                    only runs it.
                  </li>
                  <li>
                    Download {formatSize(build.size)} from{" "}
                    <code>{build.url}</code>, checked against its pinned
                    SHA-256.
                  </li>
                </ul>
                {running && (
                  <>
                    <p>{job?.phase}</p>
                    <progress max={1} value={job?.progress} />
                  </>
                )}
                {job?.state === "failed" && (
                  <p className="error">{job.error}</p>
                )}
                <div className="cache-actions">
                  {running ? (
                    <button
                      className="button"
                      onClick={() =>
                        void api("/ffmpeg/cancel", { method: "POST" }).catch(
                          (e) => set({ error: String(e) }),
                        )
                      }
                    >
                      Cancel
                    </button>
                  ) : (
                    <button className="primary" onClick={() => void install()}>
                      <Download size={15} />
                      Download and install
                    </button>
                  )}
                  <button
                    className="button"
                    disabled={running}
                    onClick={onClose}
                  >
                    Later
                  </button>
                </div>
              </>
            ) : (
              <p>
                No FFmpeg build is pinned for this system. Install FFmpeg{" "}
                {data.minimum} or newer with your package manager, or put{" "}
                <code>ffmpeg</code> and <code>ffprobe</code> in{" "}
                <code>{data.target}</code>, then open this window again.
              </p>
            )}
          </>
        )}
      </section>
    </div>
  );
}
