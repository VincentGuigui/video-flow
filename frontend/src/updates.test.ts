import { describe, expect, it } from "vitest";
import { offerAtStart, updateProgress, type UpdateState } from "./updates";

const state = (over: Partial<UpdateState>): UpdateState => ({
  current: "0.36.0",
  release: { version: "0.37.0", page: "", notes: [], archive: null, size: 0 },
  newer: true,
  installable: true,
  reason: null,
  skipped: false,
  enabled: true,
  job: null,
  ...over,
});

describe("update offer at start", () => {
  it("offers a newer version that is not skipped, when the check is on", () => {
    expect(offerAtStart(state({}))).toBe(true);
    expect(offerAtStart(state({ newer: false }))).toBe(false);
    expect(offerAtStart(state({ skipped: true }))).toBe(false);
    expect(offerAtStart(state({ enabled: false }))).toBe(false);
  });
  it("offers a version it cannot install, with the download page", () => {
    expect(offerAtStart(state({ installable: false }))).toBe(true);
  });
});

describe("update progress in the header", () => {
  const job = (state: "running" | "ready" | "failed", progress = 0.426) =>
    state0({ job: { state, progress, phase: "", error: null } });
  const state0 = (over: Partial<UpdateState>) => state(over);
  it("shows a running download and an update ready to restart", () => {
    expect(updateProgress(job("running"))).toEqual({
      label: "Updating 43%",
      ready: false,
    });
    expect(updateProgress(job("ready", 1))).toEqual({
      label: "Restart to update",
      ready: true,
    });
  });
  it("shows nothing without a download, or after a failure", () => {
    expect(updateProgress(null)).toBeNull();
    expect(updateProgress(state({}))).toBeNull();
    expect(updateProgress(job("failed"))).toBeNull();
  });
});
