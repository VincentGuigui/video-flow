import { describe, expect, it } from "vitest";
import { defaultTransform, type Clip, type Document } from "./model";
import { assemblyFrame, assemblyRange } from "./transcript";

const clip = (id: string, start: number, sourceIn: number): Clip => ({
  id,
  kind: "video",
  assetId: "asset",
  name: id,
  start,
  sourceIn,
  sourceOut: sourceIn + 100,
  layer: 0,
  enabled: true,
  linkId: null,
  gainDb: 0,
  transform: defaultTransform(),
});
const doc = (): Document => ({
  version: 1,
  clips: [clip("first", 0, 0), clip("second", 100, 50)],
});

describe("transcript timecodes", () => {
  it("maps source time to the assembly through the clip trim", () => {
    // 3 s at 25 fps = source frame 75, 25 frames after the trimmed head.
    expect(assemblyFrame(doc(), "second", 3_000_000, 25)).toBe(125);
    expect(assemblyFrame(doc(), "second", 1_000_000, 25)).toBeNull();
    expect(assemblyFrame(doc(), "second", 7_000_000, 25)).toBeNull();
  });
  it("is unavailable for disabled clips", () => {
    const d = doc();
    d.clips[1].enabled = false;
    expect(assemblyFrame(d, "second", 3_000_000, 25)).toBeNull();
  });
  it("clamps section ranges to the trimmed clip", () => {
    expect(assemblyRange(doc(), "second", 0, 4_000_000, 25)).toEqual({
      start: 100,
      end: 150,
    });
    expect(assemblyRange(doc(), "second", 0, 1_000_000, 25)).toBeNull();
  });
});
