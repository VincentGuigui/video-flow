import { describe, expect, it } from "vitest";
import { defaultTransform, type Clip } from "./model";
import { amount, ramps, zoomAt, zoomForRange, type Zoom } from "./zoom";

const Z: Zoom = {
  start: 10,
  end: 40,
  scale: 3,
  x: 0.2,
  y: 0.8,
  easeIn: 10,
  easeOut: 10,
};
const clip = (zooms: Zoom[] = [Z], speed = 1): Clip => ({
  id: "c",
  kind: "video",
  assetId: "a",
  name: "c",
  start: 100,
  sourceIn: 0,
  sourceOut: 50,
  layer: 0,
  enabled: true,
  linkId: null,
  gainDb: 0,
  transform: defaultTransform(),
  zooms,
  speed,
});

describe("zoom (mirrors backend tests)", () => {
  it("eases in, holds and eases out", () => {
    expect(amount(Z, 9)).toBe(0);
    expect(amount(Z, 15)).toBeCloseTo(0.5);
    expect(amount(Z, 25)).toBe(1);
    expect(amount(Z, 40)).toBe(0);
    expect(ramps({ ...Z, start: 0, end: 10, easeIn: 8, easeOut: 8 })).toEqual([
      8, 2,
    ]);
  });
  it("maps timeline frames to the clip's source time, with speed", () => {
    expect(zoomAt(clip(), 125)).toEqual({ factor: 3, x: 0.2, y: 0.8 });
    expect(zoomAt(clip([Z], 2), 112).factor).toBe(3); // source 24 at 2x
    expect(zoomAt(clip(), 99).factor).toBe(1);
  });
  it("builds a zoom from a timeline range inside the clip", () => {
    const z = zoomForRange(clip([]), { start: 110, end: 130 }, 30)!;
    expect([z.start, z.end, z.scale, z.easeIn, z.easeOut]).toEqual([
      10, 30, 2, 9, 30,
    ]);
    expect(zoomForRange(clip([]), { start: 0, end: 50 }, 30)).toBeNull();
  });
});
