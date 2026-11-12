// Preview media of each source (docs/features/import-analysis/importing.md#preview-media):
// stills and sound right after import, then the WebM video made in the background.
import { create } from "zustand";
import { api } from "./store";

export interface PreviewState {
  video: boolean;
  audio: boolean;
  stills: number;
  state: "ready" | "stills" | "pending" | "failed";
  progress: number | null;
  error: string | null;
}

interface Previews {
  states: Record<string, PreviewState>;
  refresh: () => Promise<void>;
}

const POLL_MS = 1500;
let timer: ReturnType<typeof setTimeout> | undefined;

export const usePreviews = create<Previews>((set, get) => ({
  states: {},
  refresh: async () => {
    clearTimeout(timer);
    try {
      const states = await api<Record<string, PreviewState>>("/previews");
      if (JSON.stringify(states) !== JSON.stringify(get().states))
        set({ states });
      // Poll while a preview is still being made.
      if (Object.values(states).some((s) => s.state !== "ready"))
        timer = setTimeout(() => void get().refresh(), POLL_MS);
    } catch {
      timer = setTimeout(() => void get().refresh(), POLL_MS * 4);
    }
  },
}));

export const usePreview = (assetId: string | null) =>
  usePreviews((s) => (assetId ? s.states[assetId] : undefined));

// What the preview plays: the video once ready, else the sound (with a different URL so
// the media element reloads when the video replaces it).
export const mediaUrl = (assetId: string | null, state?: PreviewState) =>
  `/api/media/${assetId}${state && !state.video && state.audio ? "?part=audio" : ""}`;

export const stillUrl = (assetId: string | null, second: number) =>
  `/api/previews/${assetId}/still/${Math.max(0, Math.floor(second))}`;

// The source has something playable: its video, or its sound for an audio clip.
export const playable = (state: PreviewState | undefined, audio: boolean) =>
  !!state &&
  (state.video || (audio && (state.audio || state.state === "ready")));
