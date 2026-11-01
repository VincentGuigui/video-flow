import { describe, expect, it } from "vitest";
import { defaultTransform, trim, type Clip, type Document } from "./model";
import {
  addKeyframe,
  clearKeyframes,
  moveKeyframe,
  removeKeyframe,
  setTransformAt,
  transformAt,
  transformAtFrame,
  visibleKeyframes,
} from "./keyframes";

// Keyframed transforms (docs/features/keyframes.md); mirrors the backend tests.
const at = (x: number, extra = {}) => ({ ...defaultTransform(), x, ...extra });
const clip = (extra: Partial<Clip> = {}): Clip => ({
  id: "v",
  kind: "video",
  linkId: null,
  assetId: "a",
  name: "v",
  start: 100,
  sourceIn: 10,
  sourceOut: 60,
  layer: 0,
  enabled: true,
  gainDb: 0,
  transform: at(0),
  ...extra,
});
const doc = (c: Clip): Document => ({
  version: 1,
  clips: [c],
  transitions: [],
});

describe("keyframes", () => {
  const keyed = clip({
    keyframes: [
      { frame: 10, transform: at(0), ease: "linear" },
      { frame: 20, transform: at(100, { rotation: 90, opacity: 0 }) },
      { frame: 30, transform: at(0) },
    ],
  });

  it("interpolate between keyframes and hold outside them", () => {
    expect(transformAt(keyed, 0).x).toBe(0);
    expect(transformAt(keyed, 15)).toMatchObject({
      x: 50,
      rotation: 45,
      opacity: 0.5,
    });
    expect(transformAt(keyed, 22.5).x).toBeCloseTo(100 - 100 * 0.15625);
    expect(transformAt(keyed, 40).x).toBe(0);
    // Timeline frame 105 shows source frame 15.
    expect(transformAtFrame(keyed, 105).x).toBe(50);
    expect(transformAt(clip(), 15).x).toBe(0);
  });

  it("auto-key an edit at the cursor once the clip has keyframes", () => {
    const plain = setTransformAt(doc(clip()), "v", 105, at(7), clip());
    expect(plain.clips[0].transform.x).toBe(7);
    const d = setTransformAt(doc(keyed), "v", 115, at(5), keyed);
    expect(d.clips[0].keyframes!.map((k) => [k.frame, k.transform.x])).toEqual([
      [10, 0],
      [20, 100],
      [25, 5],
      [30, 0],
    ]);
    const replaced = setTransformAt(doc(keyed), "v", 110, at(9), keyed);
    expect(replaced.clips[0].keyframes![1]).toMatchObject({
      frame: 20,
      ease: "smooth",
    });
    expect(replaced.clips[0].keyframes![1].transform.x).toBe(9);
  });

  it("add, move inside the visible range, remove and clear keyframes", () => {
    const added = addKeyframe(doc(keyed), "v", 105, keyed);
    expect(added.clips[0].keyframes![1]).toMatchObject({ frame: 15 });
    expect(added.clips[0].keyframes![1].transform.x).toBe(50);
    expect(addKeyframe(doc(keyed), "v", 110, keyed)).toEqual(doc(keyed));
    const moved = moveKeyframe(doc(keyed), "v", 20, 500);
    expect(moved.clips[0].keyframes!.map((k) => k.frame)).toEqual([10, 30, 59]);
    expect(moveKeyframe(doc(keyed), "v", 20, 30)).toEqual(doc(keyed)); // occupied
    const last = removeKeyframe(
      doc(clip({ keyframes: [{ frame: 12, transform: at(3) }] })),
      "v",
      12,
    );
    expect(last.clips[0]).toMatchObject({ keyframes: [], transform: { x: 3 } });
    const cleared = clearKeyframes(doc(keyed), "v", 105, keyed);
    expect(cleared.clips[0].keyframes).toEqual([]);
    expect(cleared.clips[0].transform.x).toBe(50);
  });

  it("show only keyframes inside the clip and follow still-clip head trims", () => {
    const trimmed = clip({ sourceIn: 15, keyframes: keyed.keyframes });
    expect(visibleKeyframes(trimmed).map((k) => k.frame)).toEqual([20, 30]);
    const still = clip({
      sourceIn: 0,
      sourceOut: 90,
      start: 30,
      stillFrame: 0,
      keyframes: [{ frame: 10, transform: at(1) }],
    });
    const extended = trim(doc(still), "v", "in", -30, true, 1);
    expect(extended.clips[0].keyframes![0].frame).toBe(40);
  });
});
