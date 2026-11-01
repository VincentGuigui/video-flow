import { useEffect, useRef, useState, type ReactNode } from "react";
import {
  Settings as SettingsIcon,
  Maximize2,
  Minimize2,
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
  Type,
  Sparkles,
  Image as ImageIcon,
  Diamond,
} from "lucide-react";
import {
  canRestoreAudio,
  clone,
  detach,
  fitPicture,
  nextFitMode,
  linkCandidates,
  linkClips,
  duration,
  fps,
  freezeAtCursor,
  isStill,
  keyboardStep,
  layout,
  pack,
  remove,
  resize,
  restoreAudio,
  split,
  timecode,
  type Asset,
  type Clip,
} from "../model";
import { api, updateClip, useEditor, flushClipUpdates } from "../store";
import { Settings, type SettingsData } from "./Settings";
import { ManageModels } from "./ManageModels";
import { FfmpegSetup, type FfmpegState } from "./FfmpegSetup";
import { InterfaceZoom } from "./InterfaceZoom";
import { RenderPanel } from "./RenderPanel";
import { Home } from "./Home";
import { ProjectSave } from "./ProjectSave";
import { TransformInput } from "./TransformInput";
import { Preview } from "./Preview";
import { Flow } from "./Flow";
import { Transport } from "./Transport";
import { Transcript } from "./Transcript";
import { Compare } from "./Compare";
import { removeClips, withoutAssets, zoneItems } from "../zones";
import { TitleControls } from "./TitleControls";
import { EffectsTab } from "./EffectsTab";
import { AnimationTab } from "./AnimationTab";
import { stackedTakes } from "../compare";
import { useAnalysis } from "./useAnalysis";
import { currentRange, currentWindow, togglePlay } from "../playback";
import { autoTrim, deleteRange, trimToRange } from "../range";
import { ImportDialog } from "./Imports";
import { MediaInfoDialog, MediaMenu } from "./MediaInfo";
import { native, type NativeFile, type NativeSelection } from "../desktop";
import { PropertiesDock } from "./PropertiesDock";
import { addKeyframe, removeKeyframe } from "../keyframes";
import { loadLayout, storeLayout } from "../panel";

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
    [mediaMenu, setMediaMenu] = useState<{
      asset: Asset;
      x: number;
      y: number;
    } | null>(null),
    [mediaInfo, setMediaInfo] = useState<Asset | null>(null),
    [reanalyse, setReanalyse] = useState<Asset | null>(null),
    [settings, setSettings] = useState(false),
    [modelPrompt, setModelPrompt] = useState(false),
    [ffmpegPrompt, setFfmpegPrompt] = useState(false),
    [help, setHelp] = useState(false),
    [drag, setDrag] = useState(false),
    [output, setOutput] = useState(false),
    [outputMessage, setOutputMessage] = useState(""),
    [exporting, setExporting] = useState(false),
    [panel, setPanel] = useState(loadLayout);
  const picker = useRef<HTMLInputElement>(null);
  const resolved = layout(document),
    rate = project ? fps(project.settings) : 30,
    // The home page shows when the logo closed the project or none is open at launch.
    showHome = home || state.closed;
  const selectedClip = document.clips.find((c) => c.id === selected),
    focused = resolved.clips.find((c) => c.id === focus);
  useEffect(() => storeLayout(panel), [panel]);
  const dock = (
    <PropertiesDock layout={panel} onChange={setPanel}>
      {(controls) => <Inspector clip={selectedClip} controls={controls} />}
    </PropertiesDock>
  );
  useEffect(() => {
    // The desktop window title follows the page title (desktop/host.py).
    window.document.title = project
      ? `${project.name} — Video-Flow`
      : "Video-Flow";
  }, [project?.name]);
  useEffect(() => {
    void load();
    // FFmpeg first: without it nothing can be imported or rendered.
    void api<FfmpegState>("/ffmpeg")
      .then((data) => setFfmpegPrompt(!data.available))
      .catch((e) => set({ error: String(e) }));
    void api<SettingsData>("/settings")
      .then((data) => {
        if (
          data.preferences.analyseImports &&
          data.models.some((m) => m.required && m.state !== "up-to-date")
        ) {
          setModelPrompt(true);
        }
      })
      .catch((e) => set({ error: String(e) }));
  }, [load, set]);
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
      initialFrame = frame,
      window = currentWindow();
    const tick = (now: number) => {
      const s = useEditor.getState(),
        fpsValue = s.project ? fps(s.project.settings) : 30;
      const next =
        initialFrame + Math.floor(((now - initial) / 1000) * fpsValue);
      if (next >= window.end) {
        s.set({ frame: window.start, playing: false });
        return;
      }
      s.set({ frame: next });
      id = requestAnimationFrame(tick);
    };
    id = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(id);
    // The playback clock and window are fixed per play action; seeking stops playback.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [playing]);
  useEffect(() => set({ range: null, rangeHandle: null }), [focus]);
  useEffect(() => {
    const r = layout(document);
    if (frame >= r.total) set({ frame: Math.max(0, r.total - 1) });
  }, [document]);
  useEffect(() => {
    function keyboard(e: KeyboardEvent) {
      const target = e.target as HTMLElement;
      if (
        target.closest('input,textarea,select,[contenteditable="true"]') ||
        settings ||
        modelPrompt ||
        ffmpegPrompt ||
        home ||
        useEditor.getState().closed ||
        importFiles ||
        help ||
        output ||
        useEditor.getState().compare
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
        togglePlay();
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
        if (s.rangeHandle) s.set({ rangeHandle: null });
        else s.set({ selected: null, focus: null, selectedAssets: [] });
      }
      if (ctrl && e.key.toLowerCase() === "a" && s.zone) {
        e.preventDefault();
        const ids = zoneItems(s.zone, s.document, p, s.frame);
        if (s.zone === "media") s.set({ selectedAssets: ids });
        else s.set({ selected: null, selectedClips: ids });
        return;
      }
      if (ctrl && e.key.toLowerCase() === "z") {
        e.preventDefault();
        void (e.shiftKey ? s.redo() : s.undo());
      }
      if (ctrl && e.key.toLowerCase() === "y") {
        e.preventDefault();
        void s.redo();
      }
      const clipIds = s.selectedClips.length
        ? s.selectedClips
        : s.selected
          ? [s.selected]
          : [];
      if (
        !s.busy &&
        (e.key === "Delete" || e.key === "Backspace") &&
        s.keyframe !== null &&
        s.selected &&
        s.zone === "timeline"
      ) {
        // A keyframe selected on the timeline is removed, not its clip.
        e.preventDefault();
        void s.save(removeKeyframe(s.document, s.selected, s.keyframe));
        s.set({ keyframe: null });
        return;
      }
      if (s.selected && !s.busy && e.key.toLowerCase() === "k" && !ctrl) {
        const placed = layout(s.document).clips.find(
          (c) => c.id === s.selected,
        );
        if (
          placed?.kind === "video" &&
          s.frame >= placed.start &&
          s.frame < placed.start + duration(placed)
        ) {
          e.preventDefault();
          void s.save(addKeyframe(s.document, placed.id, s.frame, placed));
        }
      }
      if (!s.busy && (e.key === "Delete" || e.key === "Backspace")) {
        if (s.zone === "media" && s.selectedAssets.length) {
          // Removing media also removes its clips; one undo step restores both.
          e.preventDefault();
          void s.save(
            withoutAssets(s.document, s.selectedAssets),
            undefined,
            s.selectedAssets.map((assetId) => ({
              type: "RemoveAsset",
              assetId,
            })),
          );
          s.set({ selectedAssets: [], selected: null, focus: null });
        } else if (clipIds.length) {
          e.preventDefault();
          void s.save(removeClips(s.document, clipIds, e.key === "Backspace"));
          s.set({ selected: null, focus: null, playing: false });
        }
      }
      if (s.selected && !s.busy && e.key.toLowerCase() === "s" && !ctrl) {
        e.preventDefault();
        void s.save(split(pack(s.document), s.selected, s.frame));
      }
      if (s.selected && !s.busy && e.key.toLowerCase() === "f" && !ctrl) {
        const frozen = freezeAtCursor(s.document, s.selected, s.frame, rate);
        if (frozen) {
          e.preventDefault();
          void s.save(frozen.doc);
          s.set({ selected: frozen.id });
        }
      }
      if (e.key === "?") setHelp(true);
    }
    window.addEventListener("keydown", keyboard);
    return () => window.removeEventListener("keydown", keyboard);
  }, [settings, modelPrompt, ffmpegPrompt, home, importFiles, help, output]);
  // The home page closes the project: the server releases its workers and files, and
  // the editor unmounts its media. Opening or creating a project loads it again.
  async function closeProject() {
    await flushClipUpdates();
    try {
      await api("/projects/action", {
        method: "POST",
        body: JSON.stringify({ kind: "close" }),
      });
    } catch (e) {
      set({ error: String(e) });
      return;
    }
    set({
      closed: true,
      project: null,
      document: { version: 1, clips: [] },
      selected: null,
      selectedClips: [],
      selectedAssets: [],
      focus: null,
      frame: 0,
      range: null,
      rangeHandle: null,
      compare: null,
      playing: false,
      history: [],
      future: [],
    });
    setHome(true);
  }
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
    await flushClipUpdates();
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
        <a
          className="brand"
          href="#home"
          aria-label="Video-Flow"
          onClick={(e) => {
            e.preventDefault();
            void closeProject();
          }}
        >
          <span className="brand-mark">
            <Film size={19} />
          </span>
          video<span className="brand-flow">flow</span>
        </a>
        <div className="header-divider" />

        <span className={`save-status ${busy ? "saving" : ""}`}>
          <span className="status-dot" />
          {busy ? "Saving…" : "All changes saved"}
        </span>
        <div className="header-actions">
          <button
            className="icon-button"
            aria-label="Settings"
            title="Settings"
            onClick={() => {
              setModelPrompt(false);
              setSettings(true);
            }}
          >
            <SettingsIcon size={18} />
          </button>
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
      {showHome && <Home onClose={() => setHome(false)} />}
      <div
        className="workspace"
        style={showHome ? { display: "none" } : undefined}
      >
        <aside
          className={`media-library ${state.zone === "media" ? "zone-active" : ""}`}
          onPointerDownCapture={() => set({ zone: "media" })}
        >
          <div className="library-heading">
            <span>PROJECT MEDIA</span>
          </div>
          <div className="library-list">
            {project?.assets.map((asset) => (
              <div
                className={`library-asset ${state.selectedAssets.includes(asset.id) ? "selected" : ""}`}
                key={asset.id}
                onContextMenu={(e) => {
                  e.preventDefault();
                  set({ selectedAssets: [asset.id] });
                  setMediaMenu({ asset, x: e.clientX, y: e.clientY });
                }}
                onClick={(e) =>
                  set({
                    selectedAssets:
                      e.ctrlKey || e.metaKey
                        ? state.selectedAssets.includes(asset.id)
                          ? state.selectedAssets.filter((a) => a !== asset.id)
                          : [...state.selectedAssets, asset.id]
                        : [asset.id],
                  })
                }
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
                      draggable={false}
                    />
                  ) : (
                    <Music2 size={24} />
                  )}
                  <span>
                    {asset.probe.still
                      ? "Image"
                      : timecode(
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
          <div
            className={`preview-row ${panel.height === "half" && panel.pinned ? "with-panel" : ""}`}
            style={{
              gridTemplateColumns:
                panel.height === "half" && panel.pinned
                  ? `minmax(300px, 1fr) ${panel.width}px`
                  : undefined,
            }}
          >
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
            {panel.height === "half" && dock}
          </div>
          <Transport />
          <Flow />
        </main>
        {panel.height === "tall" && dock}
      </div>
      <footer className="app-footer">
        <InterfaceZoom />

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
            <p>Video, audio, images and existing analysis JSON</p>
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
      {mediaMenu && (
        <MediaMenu
          x={mediaMenu.x}
          y={mediaMenu.y}
          onClose={() => setMediaMenu(null)}
          onAnalyse={() => {
            setReanalyse(mediaMenu.asset);
            setMediaMenu(null);
          }}
          onInfo={() => {
            setMediaInfo(mediaMenu.asset);
            setMediaMenu(null);
          }}
        />
      )}
      {mediaInfo && (
        <MediaInfoDialog asset={mediaInfo} onClose={() => setMediaInfo(null)} />
      )}
      {reanalyse && (
        <ImportDialog
          selections={[]}
          reanalyse={{
            assetId: reanalyse.id,
            name: reanalyse.path.split(/[\\/]/).at(-1) ?? reanalyse.id,
          }}
          onClose={() => setReanalyse(null)}
        />
      )}
      {state.compare && <Compare clipId={state.compare} />}
      {settings && <Settings onClose={() => setSettings(false)} />}
      {ffmpegPrompt && (
        <FfmpegSetup requested onClose={() => setFfmpegPrompt(false)} />
      )}
      {modelPrompt && !ffmpegPrompt && (
        <ManageModels requested onClose={() => setModelPrompt(false)} />
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
              ["Freeze frame at cursor", "F"],
              ["Keyframe at cursor (selected clip)", "K"],
              ["Remove the selected keyframe", "Delete (timeline)"],
              ["Lift · preserve time", "Delete"],
              ["Ripple delete", "Backspace"],
              ["Select all in the clicked zone", "Ctrl + A"],
              ["Remove selected media and its clips", "Delete (media)"],
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
            <RenderPanel />
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
              [
                "Camtasia project",
                "Clips, lanes and transitions as a .tscproj",
                ["camtasia"],
              ],
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
              editors may ignore them. Use MP4 video to render the visible edit
              and audio.
            </p>
          </section>
        </div>
      )}
    </div>
  );
}

function Inspector({
  clip,
  controls,
}: {
  clip: Clip | undefined;
  controls: ReactNode;
}) {
  const selectedClips = useEditor((s) => s.selectedClips);
  const { project, document, save, busy } = useEditor();
  const tab = useEditor((s) => s.inspectorTab),
    setTab = (inspectorTab: typeof tab) =>
      useEditor.getState().set({ inspectorTab });
  const analysis = useAnalysis(clip?.assetId ?? null);
  const rate = project ? fps(project.settings) : 30;
  const candidates = clip ? linkCandidates(pack(document), clip.id) : [];
  const asset = project?.assets.find((a) => a.id === clip?.assetId);
  const video = asset?.probe.video;
  const restorable = clip ? canRestoreAudio(document, clip.id, asset) : false;
  const takes = clip ? stackedTakes(document, clip.id) : [];
  const rangeTrim = clip
    ? trimToRange(document, clip.id, currentRange())
    : null;
  const rangeDelete = clip
    ? deleteRange(document, clip.id, currentRange())
    : null;
  const padding = project?.settings.clipPadding as
    { beforeUs: number; afterUs: number } | undefined;
  const silenceTrim =
    clip && analysis?.words
      ? autoTrim(document, clip.id, analysis.words, rate, padding)
      : null;
  const fitMode =
    clip && video && project
      ? nextFitMode(clip, video, project.settings)
      : "fit";
  return (
    <div className="inspector">
      <div className="inspector-tabs">
        {(clip && clip.kind === "gap"
          ? (["Clip", "Project"] as const)
          : clip && clip.kind === "text"
            ? (["Clip", "Effects", "Project"] as const)
            : clip && isStill(clip)
              ? (["Clip", "Animation", "Effects", "Project"] as const)
              : clip && clip.kind === "audio"
                ? (["Clip", "Effects", "Transcript", "Project"] as const)
                : ([
                    "Clip",
                    "Animation",
                    "Effects",
                    "Transcript",
                    "Project",
                  ] as const)
        ).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={tab === t ? "active" : ""}
          >
            {t}
          </button>
        ))}
        {controls}
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
      ) : tab === "Transcript" &&
        clip &&
        clip.kind !== "text" &&
        !isStill(clip) ? (
        <Transcript clip={clip} />
      ) : tab === "Effects" && clip && clip.kind !== "gap" ? (
        <EffectsTab clip={clip} />
      ) : tab === "Animation" && clip && clip.kind === "video" ? (
        <AnimationTab clip={clip} />
      ) : clip ? (
        <div className="inspector-content">
          <div className={`inspector-kind ${clip.kind}`}>
            {clip.kind === "audio" ? (
              <Music2 size={16} />
            ) : clip.kind === "text" ? (
              <Type size={16} />
            ) : isStill(clip) ? (
              <ImageIcon size={16} />
            ) : (
              <Film size={16} />
            )}{" "}
            {clip.kind === "gap"
              ? "Empty clip"
              : clip.kind === "audio"
                ? "Audio clip"
                : clip.kind === "text"
                  ? "Text clip"
                  : asset?.probe.still
                    ? "Image clip"
                    : isStill(clip)
                      ? "Freeze frame"
                      : "Video clip"}
          </div>
          <h3 title={clip.name}>{clip.name}</h3>
          <TitleControls clip={clip} />
          {isStill(clip) && (
            <div className="inspector-section">
              <div className="stat-row">
                <span>Duration</span>
                <strong>{timecode(duration(clip), rate)}</strong>
              </div>
              <p className="muted still-hint">
                A still picture: drag either edge to make it as long as needed.
              </p>
            </div>
          )}
          {clip.kind !== "text" && !isStill(clip) && (
            <details className="inspector-section source-range" key={clip.id}>
              <summary className="overline">Source range</summary>
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
            </details>
          )}
          {clip.kind === "video" && !!clip.keyframes?.length && (
            <div className="inspector-section">
              <span className="overline">TRANSFORM</span>
              <p className="muted still-hint">
                Animated with {clip.keyframes.length} keyframe
                {clip.keyframes.length === 1 ? "" : "s"}.
              </p>
              <button
                className="button"
                onClick={() =>
                  useEditor.getState().set({ inspectorTab: "Animation" })
                }
              >
                <Diamond size={14} />
                Edit in Animation
              </button>
            </div>
          )}
          {clip.kind === "video" && !clip.keyframes?.length && (
            <div className="inspector-section">
              <span className="overline">TRANSFORM</span>
              <div className="transform-grid">
                {(["x", "y", "width", "height"] as const).map((key) => (
                  <label key={clip.id + key}>
                    {{ x: "X", y: "Y", width: "Width", height: "Height" }[key]}
                    <TransformInput clip={clip} field={key} />
                  </label>
                ))}
              </div>
              <button
                className="button fit-picture"
                disabled={busy || !video}
                onClick={() => {
                  if (!video || !project) return;
                  updateClip(clip.id, {
                    transform: fitPicture(
                      video,
                      project.settings,
                      fitMode === "fill",
                    ),
                    fitMode,
                  });
                }}
              >
                {fitMode === "fill" ? (
                  <Maximize2 size={14} />
                ) : (
                  <Minimize2 size={14} />
                )}
                Scale to {fitMode}
              </button>
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
          {!clip.linkId &&
            clip.kind !== "gap" &&
            clip.kind !== "text" &&
            !isStill(clip) && (
              <div className="inspector-section">
                <label className="link-selector">
                  Link {clip.kind === "video" ? "audio" : "video"}
                  <select
                    aria-label="Link clip"
                    value=""
                    disabled={busy || !candidates.length}
                    onChange={(e) => {
                      if (!e.target.value) return;
                      try {
                        void save(
                          linkClips(
                            pack(useEditor.getState().document),
                            clip.id,
                            e.target.value,
                          ),
                        );
                      } catch (error) {
                        useEditor.getState().set({ error: String(error) });
                      }
                    }}
                  >
                    <option value="">
                      {candidates.length
                        ? "Choose a clip…"
                        : "Align starts and durations to link"}
                    </option>
                    {candidates.map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.name}
                      </option>
                    ))}
                  </select>
                </label>
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
          {restorable && (
            <button
              className="button restore-audio-action"
              disabled={busy}
              onClick={() => void save(restoreAudio(pack(document), clip.id))}
            >
              <Volume2 size={14} />
              Restore original audio
            </button>
          )}
          {takes.length > 1 && (
            <button
              className="button compare-action"
              onClick={() =>
                useEditor.getState().set({ compare: clip.id, playing: false })
              }
            >
              <Layers size={14} />
              Compare takes ({takes.length})
            </button>
          )}
          {clip.kind !== "gap" && (
            <div className="inspector-section trim-actions">
              <span className="overline">TRIM</span>
              <button
                className="button trim-range-action"
                disabled={busy || !rangeTrim}
                title="Keep only the part of the clip inside the timeline range; later clips move earlier"
                onClick={() => {
                  if (!rangeTrim) return;
                  void save(rangeTrim);
                  useEditor.getState().set({ range: null, rangeHandle: null });
                }}
              >
                <Scissors size={14} />
                Trim clip to range
              </button>
              <button
                className="button delete-range-action"
                disabled={busy || !rangeDelete}
                title="Cut the part of the clip inside the timeline range; later clips move earlier"
                onClick={() => {
                  if (!rangeDelete) return;
                  void save(rangeDelete);
                  useEditor.getState().set({ range: null, rangeHandle: null });
                }}
              >
                <Scissors size={14} />
                Delete range
              </button>
              <button
                className="button auto-trim-action"
                disabled={busy || !silenceTrim}
                title={
                  analysis?.words?.length
                    ? "Remove silence before the first and after the last word"
                    : "Needs a transcript (import with analysis)"
                }
                onClick={() => silenceTrim && void save(silenceTrim)}
              >
                <Scissors size={14} />
                Auto-trim silence
              </button>
            </div>
          )}
          {clip.kind !== "gap" && (
            <button
              className="button effects-link"
              onClick={() =>
                useEditor.getState().set({ inspectorTab: "Effects" })
              }
            >
              <Sparkles size={14} />
              Transitions & effects
            </button>
          )}
          <div className="inspector-tip">
            <Scissors size={17} />
            <p>
              {clip.kind === "audio"
                ? "Drag either edge to trim audio. Other clips stay in place."
                : "Top trim handles ripple time. Bottom handles preserve time."}
            </p>
          </div>
        </div>
      ) : (
        <div className="inspector-empty">
          <div>
            <Film size={24} />
          </div>
          {selectedClips.length > 0 ? (
            <>
              <h3>{selectedClips.length} clips selected</h3>
              <p>
                Delete lifts them, Backspace
                <br />
                ripple-deletes them.
              </p>
            </>
          ) : (
            <>
              <h3>Make it yours.</h3>
              <p>
                Select a clip in the flow
                <br />
                to see its details.
              </p>
            </>
          )}
          <span>Double-click to focus & trim</span>
        </div>
      )}
    </div>
  );
}
