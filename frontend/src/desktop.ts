export interface NativeFile {
  handle: string;
  name: string;
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
      relink: (assetId: string) => void;
    };
  }
}
export const native = () => window.__videoflowDesktop === true;
const h264 = document
  .createElement("video")
  .canPlayType('video/mp4; codecs="avc1.42E01E"');
export const mediaUrl = (assetId: string | null) =>
  `/api/media/${assetId}${h264 ? "" : "?codec=webm"}`;
