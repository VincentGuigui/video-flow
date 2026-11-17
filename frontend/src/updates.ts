// Updates from the GitHub releases (docs/features/getting-started/updates.md).
import { create } from "zustand";
export interface UpdateState {
  current: string;
  release: null | {
    version: string;
    page: string;
    notes: string[];
    archive: string | null;
    size: number;
  };
  newer: boolean;
  installable: boolean;
  reason: string | null;
  skipped: boolean;
  enabled: boolean;
  job: null | {
    state: "running" | "ready" | "cancelled" | "failed";
    progress: number;
    phase: string;
    error: string | null;
  };
}

// Offered at start: a newer release, not skipped, with the check turned on.
export const offerAtStart = (state: UpdateState) =>
  state.enabled && state.newer && !state.skipped;

// The update state, shared by the window, Settings and the header indicator, so a
// download goes on while the window is closed.
interface UpdateStore {
  state: UpdateState | null;
  open: boolean;
  set: (values: Partial<Pick<UpdateStore, "state" | "open">>) => void;
}
export const useUpdate = create<UpdateStore>((set) => ({
  state: null,
  open: false,
  set,
}));

// What the header shows while the window is closed: a download, or an update ready to
// restart into. null when there is nothing to show.
export function updateProgress(state: UpdateState | null) {
  const job = state?.job;
  if (!job) return null;
  if (job.state === "running")
    return {
      label: `Updating ${Math.round(job.progress * 100)}%`,
      ready: false,
    };
  if (job.state === "ready") return { label: "Restart to update", ready: true };
  return null;
}
