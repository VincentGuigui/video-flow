import { useEffect, useState } from "react";
import { FileText, FolderOpen, Info, ScanText, X } from "lucide-react";
import { api, useEditor } from "../store";
import { fps, timecode, type Asset } from "../model";
import { formatSize } from "./CacheSettings";

interface AssetInfo {
  path: string;
  relPath: string | null;
  online: boolean;
  size: number | null;
  sidecar: string | null;
  cachedAnalysis: string | null;
  analysis: null | {
    words: number;
    topics: number;
    summary: string;
    keywords: string[];
    summaryEngine: string;
  };
}

// Right-click menu of a project medium.
export function MediaMenu({
  x,
  y,
  onAnalyse,
  onInfo,
  onClose,
}: {
  x: number;
  y: number;
  onAnalyse: () => void;
  onInfo: () => void;
  onClose: () => void;
}) {
  useEffect(() => {
    const close = () => onClose();
    const key = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("pointerdown", close);
    window.addEventListener("keydown", key);
    window.addEventListener("blur", close);
    return () => {
      window.removeEventListener("pointerdown", close);
      window.removeEventListener("keydown", key);
      window.removeEventListener("blur", close);
    };
  }, [onClose]);
  return (
    <div
      className="context-menu"
      role="menu"
      style={{ left: x, top: y }}
      onPointerDown={(e) => e.stopPropagation()}
    >
      <button role="menuitem" onClick={onAnalyse}>
        <ScanText size={15} />
        Analysis…
      </button>
      <button role="menuitem" onClick={onInfo}>
        <Info size={15} />
        Info
      </button>
    </div>
  );
}

// Facts about one medium: file, location (shown in the file manager), analysis.
export function MediaInfoDialog({
  asset,
  onClose,
}: {
  asset: Asset;
  onClose: () => void;
}) {
  const { project, document, set } = useEditor();
  const [info, setInfo] = useState<AssetInfo | null>(null);
  useEffect(() => {
    void api<AssetInfo>(`/assets/${asset.id}/info`)
      .then(setInfo)
      .catch((e) => set({ error: String(e) }));
  }, [asset.id]);
  const reveal = (target: "media" | "analysis") =>
    void api(`/assets/${asset.id}/reveal?target=${target}`, {
      method: "POST",
    }).catch((e) => set({ error: String(e) }));
  const rate = project ? fps(project.settings) : 30;
  const video = asset.probe.video;
  const clip = document.clips.find((c) => c.assetId === asset.id);
  const name = asset.path.split(/[\\/]/).at(-1);
  return (
    <div className="modal-backdrop" onClick={onClose}>
      <section
        className="modal media-info"
        role="dialog"
        aria-label={`Info ${name}`}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="modal-heading">
          <h2>{name}</h2>
          <button aria-label="Close info" onClick={onClose}>
            <X size={18} />
          </button>
        </div>
        <dl>
          <dt>Size</dt>
          <dd>
            {info?.size != null
              ? formatSize(info.size)
              : info
                ? "Offline"
                : "…"}
          </dd>
          <dt>Duration</dt>
          <dd>
            {timecode(Math.round((asset.probe.durationUs * rate) / 1e6), rate)}
          </dd>
          {video && (
            <>
              <dt>Picture</dt>
              <dd>
                {video.width} × {video.height}
              </dd>
            </>
          )}
          <dt>Audio</dt>
          <dd>{asset.probe.audioStreams.length ? "Yes" : "No audio stream"}</dd>
          <dt>Location</dt>
          <dd>
            <button
              className="link-button"
              title="Show in the file manager"
              disabled={!info?.online}
              onClick={() => reveal("media")}
            >
              <FolderOpen size={14} />
              {asset.path}
            </button>
            {info?.relPath && (
              <small className="muted">
                Relative to the working folder: {info.relPath}
              </small>
            )}
          </dd>
          <dt>Analysis</dt>
          <dd>
            {info?.analysis ? (
              <>
                <span>
                  {info.analysis.words} words · {info.analysis.topics} topics ·{" "}
                  {info.analysis.summaryEngine}
                </span>
                {info.analysis.summary && (
                  <p className="media-summary">{info.analysis.summary}</p>
                )}
                <button
                  className="link-button"
                  title="Show the analysis JSON in the file manager"
                  onClick={() => reveal("analysis")}
                >
                  <FileText size={14} />
                  {info.sidecar ?? info.cachedAnalysis}
                </button>
                {clip && (
                  <button
                    className="link-button"
                    onClick={() => {
                      set({
                        selected: clip.id,
                        inspectorTab: "Transcript",
                      });
                      onClose();
                    }}
                  >
                    <ScanText size={14} />
                    Show transcript
                  </button>
                )}
              </>
            ) : info ? (
              "Not analysed"
            ) : (
              "…"
            )}
          </dd>
        </dl>
      </section>
    </div>
  );
}
