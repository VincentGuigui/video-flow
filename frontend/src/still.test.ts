import { describe, expect, it } from "vitest";
import {
  defaultTransform,
  duration,
  freezeFrame,
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

describe("freeze frame", () => {
  const linked = (extra: Partial<Clip> = {}) =>
    doc(
      clip("v", 0, { linkId: "p", sourceIn: 10, sourceOut: 100, ...extra }),
      clip("a", 0, {
        kind: "audio",
        linkId: "p",
        sourceIn: 10,
        sourceOut: 100,
        ...extra,
      }),
      clip("n", 90),
    );
  const spans = (d: Document) =>
    d.clips
      .toSorted((a, b) => a.start - b.start || a.kind.localeCompare(b.kind))
      .map((c) => [c.kind, c.start, duration(c), c.stillFrame ?? null]);

  it("splits the clip and its audio around a still of the cursor frame", () => {
    const result = freezeFrame(linked(), "v", 30, 75)!;
    expect(spans(result.doc)).toEqual([
      ["audio", 0, 30, null],
      ["video", 0, 30, null],
      ["video", 30, 75, 40],
      ["audio", 105, 60, null],
      ["video", 105, 60, null],
      ["video", 165, 90, null],
    ]);
    const freeze = result.doc.clips.find((c) => c.id === result.id)!;
    expect(freeze).toMatchObject({ linkId: null, sourceIn: 0, sourceOut: 75 });
    // The right part continues from the frozen frame.
    const right = result.doc.clips.find(
      (c) => c.start === 105 && c.kind === "video",
    )!;
    expect(right.sourceIn).toBe(40);
  });

  it("goes before the clip on its first frame and after it on its last", () => {
    const withTransitions = (d: Document): Document => ({
      ...d,
      transitions: [
        {
          id: "out",
          leftId: "v",
          rightId: "n",
          type: "dissolve",
          duration: 10,
        },
      ],
    });
    const before = freezeFrame(linked(), "v", 0, 75)!;
    expect(spans(before.doc).slice(0, 3)).toEqual([
      ["video", 0, 75, 10],
      ["audio", 75, 90, null],
      ["video", 75, 90, null],
    ]);
    const after = freezeFrame(withTransitions(linked()), "v", 89, 75)!;
    expect(spans(after.doc)).toEqual([
      ["audio", 0, 90, null],
      ["video", 0, 90, null],
      ["video", 90, 75, 99],
      ["video", 165, 90, null],
    ]);
    expect(after.doc.transitions).toEqual([
      {
        id: "out",
        leftId: after.id,
        rightId: "n",
        type: "dissolve",
        duration: 10,
      },
    ]);
  });

  it("refuses still clips and frames outside the clip", () => {
    expect(freezeFrame(linked(), "v", 90, 75)).toBeNull();
    expect(
      freezeFrame(doc(clip("s", 0, { stillFrame: 3 })), "s", 5, 75),
    ).toBeNull();
    expect(freezeFrame(linked(), "a", 5, 75)).toBeNull();
  });
});
