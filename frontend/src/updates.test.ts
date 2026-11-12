import { describe, expect, it } from "vitest";
import { offerAtStart, type UpdateState } from "./updates";

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
