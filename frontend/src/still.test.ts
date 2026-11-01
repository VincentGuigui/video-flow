import { describe, expect, it } from "vitest";
import {
  defaultTransform,
  duration,
  setSpeed,
  split,
  trim,
  type Clip,
  type Document,
} from "./model";
import { activeTransitions } from "./transitions";
import { EFFECTS } from "./effects";

// Still clips (docs/features/still-images.md): one picture held for any length.
const clip = (id: string, start: number, extra: Partial<Clip> = {}): Clip => ({
  id,
  kind: "video",
  linkId: null,
  assetId: id,
  name: id,
  start,
  sourceIn: 0,
  sourceOut: 90,
  layer: 0,
  enabled: true,
  gainDb: 0,
  transform: defaultTransform(),
  ...extra,
});
const doc = (...clips: Clip[]): Document => ({
  version: 1,
  clips,
  transitions: [],
});

describe("still clips", () => {
  it("extend past any source on both edges and keep their range at 0", () => {
    const d = doc(clip("s", 30, { stillFrame: 0 }));
    const longer = trim(d, "s", "out", 500, true, 1);
    expect(duration(longer.clips[0])).toBe(590);
    const earlier = trim(d, "s", "in", -30, true, 1);
    expect(earlier.clips[0]).toMatchObject({ sourceIn: 0, sourceOut: 120 });
    // A moving clip stops at its source.
    const moving = trim(doc(clip("v", 30)), "v", "out", 500, true, 90);
    expect(duration(moving.clips[0])).toBe(90);
  });

  it("keep their held frame when split and ignore speed", () => {
    const d = doc(clip("s", 0, { stillFrame: 42 }));
    const parts = split(d, "s", 30).clips;
    expect(parts.map((c) => [duration(c), c.stillFrame])).toEqual([
      [30, 42],
      [60, 42],
    ]);
    expect(setSpeed(d, "s", 2)).toBe(d);
    const speed = EFFECTS.find((e) => e.id === "speed")!;
    expect(speed.applies(d, d.clips[0])).toBe(false);
  });

  it("give a dissolve full handles", () => {
    const d = {
      ...doc(clip("a", 0, { stillFrame: 0 }), clip("b", 90, { stillFrame: 0 })),
      transitions: [
        {
          id: "t",
          leftId: "a",
          rightId: "b",
          type: "dissolve" as const,
          duration: 20,
        },
      ],
    };
    const [active] = activeTransitions(d, () => 1);
    expect([active.before, active.after]).toEqual([10, 10]);
  });
});
