// Updates from the GitHub releases (docs/features/getting-started/updates.md).
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
