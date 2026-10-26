import { describe, expect, it } from "vitest";
import {
  defaultTransform,
  layout,
  partners,
  type Clip,
  type Document,
} from "./model";
import {
  autoTrim,
  defaultRange,
  moveHandle,
  playStart,
  playWindow,
  trimToRange,
} from "./range";

const c = (
  id: string,
  start: number,
  kind: Clip["kind"] = "video",
  linkId: string | null = null,
): Clip => ({
  id,
  kind,
  linkId,
  assetId: "asset",
  name: id,
  start,
  sourceIn: 0,
  sourceOut: 100,
  layer: 0,
  enabled: true,
  gainDb: 0,
  transform: defaultTransform(),
});
const doc = (): Document => ({
  version: 1,
  clips: [c("v", 0, "video", "p"), c("a", 0, "audio", "p"), c("next", 100)],
});

describe("range selector", () => {
  it("defaults to the focused clip with two seconds of context", () => {
    expect(defaultRange(doc(), null, 25)).toEqual({ start: 0, end: 200 });
    expect(defaultRange(doc(), "next", 25)).toEqual({ start: 50, end: 200 });
  });
  it("plays two seconds around a selected handle", () => {
    const range = { start: 60, end: 150 };
    expect(playWindow(range, null, 25, 200)).toEqual(range);
    expect(playWindow(range, "start", 25, 200)).toEqual({
      start: 10,
      end: 110,
    });
    expect(playWindow(range, "end", 25, 200)).toEqual({ start: 100, end: 200 });
  });
  it("starts at the cursor only inside the window", () => {
    expect(playStart({ start: 10, end: 50 }, 30)).toBe(30);
    expect(playStart({ start: 10, end: 50 }, 49)).toBe(10);
    expect(playStart({ start: 10, end: 50 }, 80)).toBe(10);
  });
  it("keeps handles ordered", () => {
    expect(moveHandle({ start: 10, end: 50 }, "start", 70, 200)).toEqual({
      start: 49,
      end: 50,
    });
    expect(moveHandle({ start: 10, end: 50 }, "end", -5, 200)).toEqual({
      start: 10,
      end: 11,
    });
  });
});

describe("trim to range", () => {
  it("trims both linked media and ripples later clips", () => {
    const next = trimToRange(doc(), "v", { start: 20, end: 70 })!;
    const pair = partners(next, "v");
    expect(pair.map((p) => [p.sourceIn, p.sourceOut])).toEqual([
      [20, 70],
      [20, 70],
    ]);
    expect(layout(next).clips.find((p) => p.id === "next")!.start).toBe(50);
    expect(layout(next).total).toBe(150);
  });
  it("is unavailable when the range does not shorten the clip", () => {
    expect(trimToRange(doc(), "v", { start: 0, end: 150 })).toBeNull();
    expect(trimToRange(doc(), "v", { start: 120, end: 150 })).toBeNull();
  });
});

describe("auto-trim", () => {
  it("keeps padding around the first and last words", () => {
    // 25 fps: words from 1 s to 2 s; 0.2 s before and 0.4 s after.
    const words = [
      { startUs: 1_000_000, endUs: 1_400_000 },
      { startUs: 1_500_000, endUs: 2_000_000 },
    ];
    const next = autoTrim(doc(), "v", words, 25, {
      beforeUs: 200_000,
      afterUs: 400_000,
    })!;
    const v = next.clips.find((p) => p.id === "v")!;
    expect([v.sourceIn, v.sourceOut]).toEqual([20, 60]);
    expect(layout(next).clips.find((p) => p.id === "next")!.start).toBe(40);
  });
  it("does nothing without speech", () => {
    expect(autoTrim(doc(), "v", [], 25)).toBeNull();
  });
});
