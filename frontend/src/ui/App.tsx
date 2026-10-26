import { useEffect, useRef, useState } from "react";
import {
  ArrowUpRight,
  Check,
  ChevronDown,
  Film,
  FolderOpen,
  HelpCircle,
  Import,
  Layers,
  Link2,
  Music2,
  Plus,
  Redo2,
  Undo2,
  Upload,
  Volume2,
  X,
  Scissors,
  Download,
} from "lucide-react";
import {
  clone,
  detach,
  duration,
  fps,
  keyboardStep,
  layout,
  pack,
  remove,
  resize,
  split,
  timecode,
  type Clip,
} from "../model";
import { api, updateClip, useEditor } from "../store";
import { Home } from "./Home";
import { ProjectSave } from "./ProjectSave";
import { Preview } from "./Preview";
import { Flow } from "./Flow";
import { Transport } from "./Transport";
import { ImportDialog } from "./Imports";
import { native, type NativeFile, type NativeSelection } from "../desktop";

const RESOLUTIONS = [
  [1920, 1080, "16:9 · Landscape"],
  [1080, 1920, "9:16 · Portrait"],
  [1440, 1080, "4:3 · Landscape"],
  [1080, 1440, "3:4 · Portrait"],
  [1080, 1080, "1:1 · Square"],
  [3840, 2160, "16:9 · 4K"],
  [2160, 3840, "9:16 · Portrait 4K"],
  [1280, 720, "16:9 · HD"],
  [720, 1280, "9:16 · Portrait HD"],
] as const;
export function App() {
  const state = useEditor(),
    {
      project,
      document,
      selected,
      focus,
      playing,
      frame,
      busy,
      load,
      set,
      save,
      undo,
      redo,
      history,
      future,
      error,
    } = state;
  const [importFiles, setImportFiles] = useState<NativeFile[] | null>(null),
    [home, setHome] = useState(false),
    [help, setHelp] = useState(false),
    [drag, setDrag] = useState(false),
    [output, setOutput] = useState(false),
    [outputMessage, setOutputMessage] = useState(""),
    [exporting, setExporting] = useState(false);
  const picker = useRef<HTMLInputElement>(null);
  const resolved = layout(document),
    rate = project ? fps(project.settings) : 30;
  const selectedClip = document.clips.find((c) => c.id === selected),
    focused = resolved.clips.find((c) => c.id === focus);
  useEffect(() => {
    void load();
  }, [load]);
  useEffect(() => {
    const selection = (event: Event) => {
      const detail = (event as CustomEvent<NativeSelection>).detail;
      if (detail.assetId) {
        void api<{ inverses: Record<string, unknown>[] }>("/native-relink", {
          method: "POST",
          body: JSON.stringify({
            handle: detail.selections[0].handle,
            assetId: detail.assetId,
          }),
        })
          .then(async (result) => {
            await load();
            const state = useEditor.getState();
            set({ history: [...state.history, result.inverses], future: [] });
          })
          .catch((error) => set({ error: String(error) }));
      } else setImportFiles(detail.selections);
    };
    const error = (event: Event) =>
      set({ error: (event as CustomEvent<string>).detail });
    window.addEventListener("videoflow-selection", selection);
    window.addEventListener("videoflow-error", error);
    return () => {
      window.removeEventListener("videoflow-selection", selection);
      window.removeEventListener("videoflow-error", error);
    };
  }, [load, set]);
  useEffect(() => {
    if (!playing) return;
    let id = 0;
    const initial = performance.now(),
      initialFrame = frame;
    const tick = (now: number) => {
      const s = useEditor.getState(),
        r = layout(s.document),
        fpsValue = s.project ? fps(s.project.settings) : 30,
        clip = r.clips.find((c) => c.id === s.focus);
      const end = clip
        ? Math.min(
            r.total,
            clip.start + duration(clip) + Math.round(fpsValue * 2),
          )
        : r.total;
      const next =
        initialFrame + Math.floor(((now - initial) / 1000) * fpsValue);
      if (next >= end) {
        s.set({ frame: Math.max(0, end - 1), playing: false });
        return;
      }
      s.set({ frame: next });
      id = requestAnimationFrame(tick);
    };
    id = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(id);
    // The playback clock starts once per play action; seeking stops playback.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [playing]);
  useEffect(() => {
    const r = layout(document);
    if (frame >= r.total) set({ frame: Math.max(0, r.total - 1) });
  }, [document]);
  useEffect(() => {
    function keyboard(e: KeyboardEvent) {
      const target = e.target as HTMLElement;
      if (
        target.closest('input,textarea,select,[contenteditable="true"]') ||
        home ||
        importFiles ||
        help ||
        output
      )
        return;
      const s = useEditor.getState(),
        p = s.project;
      if (!p) return;
      const r = layout(s.document),
        rate = fps(p.settings),
        clip = r.clips.find((c) => c.id === s.focus),
        start = clip ? Math.max(0, clip.start - Math.round(rate * 2)) : 0,
        end = clip
          ? Math.min(
              r.total,
              clip.start + duration(clip) + Math.round(rate * 2),
            )
          : r.total;
      const ctrl = e.ctrlKey || e.metaKey;
      if (e.code === "Space") {
        e.preventDefault();
        s.set({
          playing: !s.playing && end > 0,
          frame: s.frame >= end - 1 ? start : s.frame,
        });
        return;
      }
      const step = keyboardStep(e.key, e.shiftKey, ctrl, rate);
      if (step !== null) {
        e.preventDefault();
        s.set({
          playing: false,
          frame:
            step === "start"
              ? start
              : step === "end"
                ? Math.max(start, end - 1)
                : Math.max(
                    start,
                    Math.min(Math.max(start, end - 1), s.frame + step),
                  ),
        });
        return;
      }
      if (e.key === "Escape") {
        e.preventDefault();
        s.set({ selected: null, focus: null });
      }
      if (ctrl && e.key.toLowerCase() === "z") {
        e.preventDefault();
        void (e.shiftKey ? s.redo() : s.undo());
      }
      if (ctrl && e.key.toLowerCase() === "y") {
        e.preventDefault();
        void s.redo();
      }
      if (
        s.selected &&
        !s.busy &&
        (e.key === "Delete" || e.key === "Backspace")
      ) {
        e.preventDefault();
        void s.save(
          remove(pack(s.document), s.selected, e.key === "Backspace"),
        );
        s.set({ selected: null, focus: null, playing: false });
      }
      if (s.selected && !s.busy && e.key.toLowerCase() === "s" && !ctrl) {
        e.preventDefault();
        void s.save(split(pack(s.document), s.selected, s.frame));
      }
      if (e.key === "?") setHelp(true);
    }
    window.addEventListener("keydown", keyboard);
    return () => window.removeEventListener("keydown", keyboard);
  }, [home, importFiles, help, output]);
  function openImport() {
    if (native()) {
      if (window.videoFlowDesktop) window.videoFlowDesktop.pickFiles();
      else
        set({
          error:
            "Native file picker is still connecting. Try again in a moment.",
        });
    } else setImportFiles([]);
  }
  async function exportFiles(formats: string[]) {
    setExporting(true);
    setOutputMessage("");
    try {
      const response = await api<{ files: string[] }>("/export", {
        method: "POST",
        body: JSON.stringify({ formats }),
      });
      setOutputMessage(
        "Saved to " + response.files[0].replace(/[\\/][^\\/]+$/, ""),
      );
    } catch (e) {
      setOutputMessage(String(e));
    } finally {
      setExporting(false);
    }
  }
  return (
    <div
      className="app"
      onDragOver={(e) => {
        if (e.dataTransfer.types.includes("Files")) {
          e.preventDefault();
          if (!native()) setDrag(true);
        }
      }}
      onDrop={(e) => {
        e.preventDefault();
        setDrag(false);
        if (!native())
          set({
            error:
              "Browser diagnostic mode imports by local path. Use the desktop app for native file drops.",
          });
      }}
    >
      <header className="app-header">
        <a className="brand" href="#home" aria-label="Video-Flow" onClick={e=>{e.preventDefault();set({playing:false});setHome(true);}}>
          <span className="brand-mark">
            <Film size={19} />
          </span>
          video<span className="brand-flow">flow</span>
          <span className="beta-badge">LOCAL</span>
        </a>
        <div className="header-divider" />
        <div className="project-title">
          <FolderOpen size={14} />
          <span>{project?.name ?? "Opening project…"}</span>
        </div>
        <span className={`save-status ${busy ? "saving" : ""}`}>
          <span className="status-dot" />
          {busy ? "Saving…" : "All changes saved"}
        </span>
        <div className="header-actions">
          <button
            className="icon-button"
            aria-label="Undo"
            title="Undo (Ctrl + Z)"
            disabled={!history.length || busy}
            onClick={() => void undo()}
          >
            <Undo2 size={17} />
          </button>
          <button
            className="icon-button"
            aria-label="Redo"
            title="Redo (Ctrl + Shift + Z)"
            disabled={!future.length || busy}
            onClick={() => void redo()}
          >
            <Redo2 size={17} />
          </button>
          <span className="action-divider" />
          <button className="button import-button" onClick={openImport}>
            <Plus size={15} />
            Import media
          </button>
          <ProjectSave />
          <button
            className="primary"
            onClick={() => {
              setOutput(true);
              setOutputMessage("");
            }}
          >
            <ArrowUpRight size={15} />
            Export
          </button>
        </div>
      </header>
      {home && <Home onClose={()=>setHome(false)} />}
      <div className="workspace" style={home ? {display:"none"} : undefined}>
        <aside className="media-library">
          <div className="library-heading">
            <span>PROJECT MEDIA</span>

          </div>
          <div className="library-list">
            {project?.assets.map((asset) => (
              <div
                className="library-asset"
                key={asset.id}
                draggable
                onDragStart={(e) => {
                  e.dataTransfer.setData(
                    "application/videoflow-asset",
                    asset.id,
                  );
                }}
              >
                <div
                  className={`asset-thumbnail ${asset.probe.video ? "" : "audio"}`}
                >
                  {asset.probe.video ? (
                    <img
                      src={`/api/thumbnail/${asset.id}`}
                      alt=""
                      style={{
                        width: "100%",
                        height: "100%",
                        objectFit: "cover",
                        borderRadius: 5,
                      }}
                    />
                  ) : (
                    <Music2 size={24} />
                  )}
                  <span>
                    {timecode(
                      Math.round((asset.probe.durationUs * rate) / 1e6),
                      rate,
                    ).slice(3)}
                  </span>
                </div>
                <strong title={asset.path}>
                  {asset.path.split(/[\\/]/).at(-1)}
                </strong>
                <small>
                  {asset.probe.video
                    ? `${asset.probe.video.width} × ${asset.probe.video.height}`
                    : "Audio"}
                  <span>●</span>
                  {state.offline.includes(asset.id) ? "Offline" : "Ready"}
                </small>
                {state.offline.includes(asset.id) && native() && (
                  <button
                    className="text-button"
                    onClick={() => window.videoFlowDesktop?.relink(asset.id)}
                  >
                    Relink original
                    <FolderOpen size={12} />
                  </button>
                )}
              </div>
            ))}
            {!project?.assets.length && (
              <div className="library-empty">
                <Layers size={26} />
                <p>
                  A little space
                  <br />
                  for your footage.
                </p>

              </div>
            )}
          </div>

          <button className="shortcuts-button" onClick={() => setHelp(true)}>
            <HelpCircle size={14} />
            Keyboard shortcuts<kbd>?</kbd>
          </button>
        </aside>
        <main>
          <div className="preview-row">
            <div className="preview-container">
              <Preview />
              <select
                className="resolution-menu"
                aria-label="Output resolution"
                value={
                  project
                    ? `${project.settings.width}x${project.settings.height}`
                    : ""
                }
                onChange={(e) => {
                  if (!project) return;
                  const [width, height] = e.target.value.split("x").map(Number);
                  void save(resize(document, project.settings, width, height), {
                    ...project.settings,
                    width,
                    height,
                  });
                }}
              >
                {project &&
                  !RESOLUTIONS.some(
                    ([w, h]) =>
                      w === project.settings.width &&
                      h === project.settings.height,
                  ) && (
                    <option
                      value={`${project.settings.width}x${project.settings.height}`}
                    >
                      {project.settings.width} × {project.settings.height}
                    </option>
                  )}
                {RESOLUTIONS.map(([w, h, label]) => (
                  <option value={`${w}x${h}`} key={`${w}x${h}`}>
                    {w} × {h} · {label}
                  </option>
                ))}
              </select>
            </div>
            <Inspector clip={selectedClip} />
          </div>
          <Transport />
          <Flow />
        </main>
      </div>
      <footer className="app-footer">

        <span>
          {resolved.total
            ? `${timecode(resolved.total, rate)} assembled`
            : "Ready when you are."}
          <span className="footer-dot">·</span>Video-Flow 0.1
        </span>
      </footer>
      {drag && (
        <div className="drop-overlay" onDragLeave={() => setDrag(false)}>
          <div>
            <Upload size={40} />
            <h2>Drop it into the flow.</h2>
            <p>Video, audio, and existing analysis JSON</p>
          </div>
        </div>
      )}
      {error && (
        <div className="error-toast" role="alert">
          <span>{error}</span>
          <button
            className="icon-button"
            aria-label="Dismiss error"
            onClick={() => set({ error: "" })}
          >
            <X size={16} />
          </button>
        </div>
      )}
      {importFiles && (
        <ImportDialog
          selections={importFiles}
          onClose={() => setImportFiles(null)}
        />
      )}
      {help && (
        <div className="modal-backdrop" onClick={() => setHelp(false)}>
          <section
            className="modal shortcuts-modal"
            role="dialog"
            aria-label="Keyboard shortcuts"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="modal-heading">
              <h2>A faster way to flow.</h2>
              <button
                className="icon-button"
                onClick={() => setHelp(false)}
                aria-label="Close shortcuts"
              >
                <X size={18} />
              </button>
            </div>
            {[
              ["Play / pause", "Space"],
              ["One frame", "← / →"],
              ["One second", "Shift + ← / →"],
              ["Ten seconds", "Ctrl + ← / →"],
              ["Beginning / end", "Home / End"],
              ["Beginning / end", "Ctrl + Shift + ← / →"],
              ["Exit clip focus", "Esc"],
              ["Split at cursor", "S"],
              ["Lift · preserve time", "Delete"],
              ["Ripple delete", "Backspace"],
              ["Undo / redo", "Ctrl + Z / Ctrl + Shift + Z"],
              ["Zoom around pointer", "Ctrl + wheel"],
              ["Stretch / symmetric handles", "Shift / Alt"],
            ].map(([label, key]) => (
              <div className="shortcut-row" key={label + key}>
                <span>{label}</span>
                <kbd>{key}</kbd>
              </div>
            ))}
          </section>
        </div>
      )}
      {output && (
        <div className="modal-backdrop">
          <section
            className="modal output-modal"
            role="dialog"
            aria-label="Export edit"
          >
            <div className="modal-heading">
              <div>
                <span className="overline">NEXT STOP, YOUR EDITOR</span>
                <h2>Take your edit with you.</h2>
              </div>
              <button
                className="icon-button"
                disabled={exporting}
                onClick={() => setOutput(false)}
                aria-label="Close export"
              >
                <X size={18} />
              </button>
            </div>
            <p className="muted">
              Exports are saved in this project's exports folder.
            </p>
            {[
              [
                "OTIO timeline",
                "Cuts, layers and Video-Flow metadata",
                ["otio"],
              ],
              [
                "Portable OTIOZ",
                "Timeline and original media in one archive",
                ["otioz"],
              ],
              [
                "EDL + paper edit",
                "V1 edit list, Markdown and CSV",
                ["edl", "paper-edit"],
              ],
              ["Subtitles", "SRT from timecoded analysis words", ["srt"]],
            ].map(([label, description, formats]) => (
              <button
                key={label as string}
                className="export-option"
                disabled={exporting}
                onClick={() => void exportFiles(formats as string[])}
              >
                <Download size={19} />
                <div>
                  <strong>{label as string}</strong>
                  <p>{description as string}</p>
                </div>
                <ArrowUpRight size={16} />
              </button>
            ))}
            {outputMessage && (
              <div className="output-result" role="status">
                {outputMessage}
              </div>
            )}
            <p className="export-note">
              Gain, fades and spatial transforms are metadata in OTIO. Other
              editors may ignore them. Layered video rendering is a separate
              upcoming step.
            </p>
          </section>
        </div>
      )}
    </div>
  );
}

function Inspector({ clip }: { clip: Clip | undefined }) {
  const { project, document, save, busy } = useEditor();
  const [tab, setTab] = useState("Clip");
  const rate = project ? fps(project.settings) : 30;
  return (
    <aside className="inspector">
      <div className="inspector-tabs">
        {["Clip", "Project"].map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={tab === t ? "active" : ""}
          >
            {t}
          </button>
        ))}
      </div>
      {tab === "Project" ? (
        <div className="inspector-content">
          <span className="overline">OUTPUT</span>
          <h3>
            {project?.settings.width} × {project?.settings.height}
          </h3>
          <p className="muted">
            {rate.toFixed(rate % 1 ? 3 : 0)} frames / second
          </p>
          <div className="inspector-tip">
            <Layers size={17} />
            <p>
              Enabled clips are composited together. Higher flow lanes appear on
              top.
            </p>
          </div>
        </div>
      ) : clip ? (
        <div className="inspector-content">
          <div className={`inspector-kind ${clip.kind}`}>
            {clip.kind === "audio" ? <Music2 size={16} /> : <Film size={16} />}{" "}
            {clip.kind === "gap"
              ? "Empty clip"
              : clip.kind === "audio"
                ? "Audio clip"
                : "Video clip"}
          </div>
          <h3 title={clip.name}>{clip.name}</h3>
          <span className="clip-state">
            <span className="status-dot" />
            {clip.linkId ? "Linked video + audio" : "Independent clip"}
          </span>
          <div className="inspector-section">
            <span className="overline">SOURCE RANGE</span>
            <div className="stat-row">
              <span>In</span>
              <strong>{timecode(clip.sourceIn, rate)}</strong>
            </div>
            <div className="stat-row">
              <span>Out</span>
              <strong>{timecode(clip.sourceOut, rate)}</strong>
            </div>
            <div className="stat-row">
              <span>Duration</span>
              <strong>{timecode(duration(clip), rate)}</strong>
            </div>
          </div>
          {clip.kind === "video" && (
            <div className="inspector-section">
              <span className="overline">TRANSFORM</span>
              <div className="transform-grid">
                {(["x", "y", "width", "height"] as const).map((key) => (
                  <label key={clip.id + key + clip.transform[key]}>
                    {{ x: "X", y: "Y", width: "Width", height: "Height" }[key]}
                    <input
                      aria-label={`Clip ${key}`}
                      type="number"
                      defaultValue={Math.round(clip.transform[key])}
                      onBlur={(e) => {
                        const value = Number(e.target.value);
                        if (
                          !Number.isFinite(value) ||
                          ((key === "width" || key === "height") && value <= 0)
                        )
                          return;
                        updateClip(clip.id, {
                          transform: { ...clip.transform, [key]: value },
                        });
                      }}
                    />
                  </label>
                ))}
              </div>
            </div>
          )}
          {clip.kind === "audio" && (
            <div className="inspector-section">
              <span className="overline">VOLUME</span>
              <div className="stat-row">
                <Volume2 size={14} />
                <input
                  aria-label="Audio gain"
                  type="range"
                  min="-60"
                  max="0"
                  defaultValue={clip.gainDb}
                  key={clip.id}
                  onPointerUp={(e) =>
                    updateClip(clip.id, {
                      gainDb: Number(e.currentTarget.value),
                    })
                  }
                  onKeyUp={(e) =>
                    updateClip(clip.id, {
                      gainDb: Number(e.currentTarget.value),
                    })
                  }
                />
                <small>{clip.gainDb} dB</small>
              </div>
            </div>
          )}
          {clip.linkId && (
            <button
              className="button detach-action"
              disabled={busy}
              onClick={() => void save(detach(document, clip.id))}
            >
              <Link2 size={14} />
              Detach audio & video
            </button>
          )}
          <div className="inspector-tip">
            <Scissors size={17} />
            <p>
              Top trim handles ripple time. Bottom handles keep time with an
              empty clip.
            </p>
          </div>
        </div>
      ) : (
        <div className="inspector-empty">
          <div>
            <Film size={24} />
          </div>
          <h3>Make it yours.</h3>
          <p>
            Select a clip in the flow
            <br />
            to see its details.
          </p>
          <span>Double-click to focus & trim</span>
        </div>
      )}
    </aside>
  );
}
