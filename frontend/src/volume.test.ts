import { describe, expect, it } from "vitest";
import { defaultTransform, type Clip, type Document } from "./model";
import { duckRanges, envelopeAt, rangeFactor, sourceRange } from "./volume";

const clip = (
  id: string,
  kind: Clip["kind"],
  start: number,
  sourceIn = 0,
): Clip => ({
  id,
  kind,
  assetId: id,
  name: id,
  start,
  sourceIn,
  sourceOut: sourceIn + 100,
  layer: kind === "audio" && id === "music" ? 1 : 0,
  enabled: true,
  linkId: null,
  gainDb: 0,
  transform: defaultTransform(),
});

describe("volume ranges (mirrors backend tests)", () => {
  const mute = {
    start: 20,
    end: 30,
    gainDb: -60,
    ramp: 4,
    kind: "mute" as const,
  };
  it("ramps outside the range and reaches the gain inside", () => {
    expect(rangeFactor(mute, 15)).toBe(1);
    expect(rangeFactor(mute, 18)).toBeCloseTo(0.5);
    expect(rangeFactor(mute, 25)).toBe(0);
    expect(rangeFactor({ ...mute, gainDb: -20, ramp: 0 }, 25)).toBeCloseTo(0.1);
    expect(
      envelopeAt({ ...clip("a", "audio", 100), volumeRanges: [mute] }, 125),
    ).toBe(0);
  });
  it("maps a timeline range to the clip's source range", () => {
    const doc: Document = { version: 1, clips: [clip("a", "audio", 0, 50)] };
    expect(sourceRange(doc, doc.clips[0], { start: 10, end: 30 })).toEqual({
      start: 60,
      end: 80,
    });
    expect(sourceRange(doc, doc.clips[0], { start: 200, end: 300 })).toBeNull();
  });
  it("ducks music under merged, padded speech of other clips", () => {
    const doc: Document = {
      version: 1,
      clips: [clip("voice", "audio", 0), clip("music", "audio", 0)],
    };
    // 25 fps: words at 1.0-1.4 s and 1.6-2.0 s (merged), and 3.0-3.2 s.
    const w = (a: number, b: number) => ({
      text: "x",
      startUs: a * 1e6,
      endUs: b * 1e6,
    });
    const ranges = duckRanges(
      doc,
      "music",
      { voice: [w(1, 1.4), w(1.6, 2), w(3, 3.2)] },
      25,
    );
    expect(ranges.map((r) => [r.start, r.end, r.gainDb, r.kind])).toEqual([
      [20, 58, -15, "duck"],
      [70, 88, -15, "duck"],
    ]);
  });
});
