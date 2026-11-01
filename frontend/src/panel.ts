// Layout of the properties panel (clip / project): width, height mode and pinning.
// Remembered per viewer in localStorage; every access tolerates a missing storage.

export type PanelHeight = "half" | "tall";
export interface PanelLayout {
  width: number;
  height: PanelHeight;
  pinned: boolean;
}

export const PANEL_MIN = 200;
export const PANEL_MAX = 640;
export const DEFAULT_PANEL: PanelLayout = {
  width: 240,
  height: "half",
  pinned: true,
};
const KEY = "videoflow.panel";

// The panel never takes more than half the editor area, nor less than its minimum.
export function clampWidth(width: number, available = Infinity): number {
  const max = Math.max(PANEL_MIN, Math.min(PANEL_MAX, available / 2));
  return Math.round(Math.min(max, Math.max(PANEL_MIN, width)));
}

export function parseLayout(raw: string | null): PanelLayout {
  try {
    const data = raw ? (JSON.parse(raw) as Partial<PanelLayout>) : {};
    return {
      width: clampWidth(
        typeof data.width === "number" ? data.width : DEFAULT_PANEL.width,
      ),
      height: data.height === "tall" ? "tall" : "half",
      pinned: data.pinned !== false,
    };
  } catch {
    return DEFAULT_PANEL;
  }
}

export function loadLayout(): PanelLayout {
  try {
    return parseLayout(window.localStorage.getItem(KEY));
  } catch {
    return DEFAULT_PANEL;
  }
}

export function storeLayout(layout: PanelLayout): void {
  try {
    window.localStorage.setItem(KEY, JSON.stringify(layout));
  } catch {
    // Private windows or blocked storage: the layout is simply not remembered.
  }
}
