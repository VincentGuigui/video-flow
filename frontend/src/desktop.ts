export interface NativeFile {
  handle: string;
  name: string;
}
export interface NativeFolder {
  handle: string;
  name: string;
  path: string;
  purpose: "workdir" | "project";
}
export interface NativeSelection {
  selections: NativeFile[];
  assetId: string | null;
}
declare global {
  interface Window {
    __videoflowDesktop?: boolean;
    videoFlowDesktop?: {
      pickFiles: () => void;
      setZoom: (factor: number) => void;
      saveRenderedVideo: (id: string) => void;
      relink: (assetId: string) => void;
      pickFolder: (purpose: "workdir" | "project") => void;
      ready?: () => void;
    };
  }
}
export const native = () => window.__videoflowDesktop === true;
// Tell the desktop host that the editor shows its first data (end of the startup
// timeline, docs/reference/desktop-runtime.md); waits for the Qt bridge if needed.
export function reportReady() {
  if (!native()) return;
  if (window.videoFlowDesktop) window.videoFlowDesktop.ready?.();
  else
    window.addEventListener(
      "videoflow-ready",
      () => window.videoFlowDesktop?.ready?.(),
      { once: true },
    );
}
const h264 = document
  .createElement("video")
  .canPlayType('video/mp4; codecs="avc1.42E01E"');
export const mediaUrl = (assetId: string | null) =>
  `/api/media/${assetId}${h264 ? "" : "?codec=webm"}`;
