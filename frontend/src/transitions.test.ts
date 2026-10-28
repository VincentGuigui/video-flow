import { describe, expect, it } from "vitest";
import { defaultTransform, split, type Clip, type Document } from "./model";
import {
  dipOpacity,
  fadeGain,
  neighbours,
  planTransitions,
  clipOpacity,
  setAllTransitions,
  setFade,
  setTransition,
  type Transition,
} from "./transitions";

const clip = (
  id: string,
  start: number,
  sourceIn = 10,
  kind: Clip["kind"] = "video",
  linkId: string | null = null,
): Clip => ({
  id,
  kind,
  linkId,
  assetId: id[0],
  name: id,
  start,
  sourceIn,
  sourceOut: sourceIn + 25,
  layer: 0,
  enabled: true,
  gainDb: 0,
  transform: defaultTransform(),
});
const doc = (transitions: Transition[], rightIn = 10): Document => ({
  version: 1,
  clips: [
    clip("l", 0, 10, "video", "p"),
    clip("la", 0, 10, "audio", "p"),
    clip("r", 25, rightIn, "video", "q"),
    clip("ra", 25, rightIn, "audio", "q"),
  ],
  transitions,
});
const t = (type: Transition["type"] = "dissolve"): Transition => ({
  id: "t",
  leftId: "l",
  rightId: "r",
  type,
  duration: 10,
});
const frames = () => 100;

describe("transitions (mirrors backend tests)", () => {
  it("dissolve overlaps clips using handles and crossfades audio", () => {
    const plan = planTransitions(doc([t()]), frames);
    const by = Object.fromEntries(plan.clips.map((c) => [c.id, c]));
    expect([by.l.sourceOut, by.la.sourceOut]).toEqual([40, 40]);
    expect([by.r.start, by.r.sourceIn, by.ra.start]).toEqual([20, 5, 20]);
    expect([...plan.videoFadeIn]).toEqual([["r", 10]]);
    expect(Object.fromEntries(plan.audioFades)).toEqual({
      la: { in: 0, out: 10 },
      ra: { in: 10, out: 0 },
    });
  });
  it("missing head handle shortens the dissolve", () => {
    const a = planTransitions(doc([t()], 0), frames).active[0];
    expect([a.before, a.after]).toEqual([0, 5]);
  });
  it("dip needs no handles and keeps clips", () => {
    const plan = planTransitions(doc([t("dip_white")], 0), frames);
    expect(plan.clips.map((c) => [c.start, c.sourceIn])).toEqual([
      [0, 10],
      [0, 10],
      [25, 0],
      [25, 0],
    ]);
    expect(plan.dips).toEqual([
      { start: 20, before: 5, after: 5, color: "#ffffff" },
    ]);
    expect(dipOpacity(plan.dips[0], 25)).toBe(1);
    expect(dipOpacity(plan.dips[0], 22)).toBeCloseTo(0.4);
    expect(dipOpacity(plan.dips[0], 30)).toBe(0);
  });
  it("ignores dormant transitions", () => {
    const plan = planTransitions(
      doc([{ ...t(), leftId: "r", rightId: "l" }]),
      frames,
    );
    expect(plan.active).toEqual([]);
  });
});

describe("transition editing", () => {
  it("finds neighbours, sets, replaces and removes a cut's transition", () => {
    const d = doc([]);
    expect(neighbours(d, "l").next?.id).toBe("r");
    expect(neighbours(d, "r").previous?.id).toBe("l");
    let next = setTransition(d, "l", "r", "dip_black", 12);
    next = setTransition(next, "l", "r", "dissolve", 8);
    expect(next.transitions).toHaveLength(1);
    expect(next.transitions![0]).toMatchObject({
      type: "dissolve",
      duration: 8,
    });
    expect(setTransition(next, "l", "r", null, 8).transitions).toEqual([]);
    expect(setAllTransitions(d, "dissolve", 15).transitions).toHaveLength(1);
  });
  it("keeps the outgoing transition when the left clip is split", () => {
    const next = split(doc([t()]), "l", 10);
    const right = next.clips.find((c) => c.kind === "video" && c.start === 10)!;
    expect(next.transitions![0].leftId).toBe(right.id);
  });
  it("fades audio gain in and out", () => {
    const c = clip("x", 0);
    expect(fadeGain({ in: 10, out: 5 }, c, 5)).toBeCloseTo(0.5);
    expect(fadeGain({ in: 10, out: 5 }, c, 22)).toBeCloseTo(0.6);
    expect(fadeGain(undefined, c, 22)).toBe(1);
  });
});

describe("edge fades (mirrors backend tests)", () => {
  it("plans clip fades, caps them and merges with a dissolve", () => {
    const d = setFade(doc([]), "l", "fadeIn", 10);
    const capped = setFade(d, "l", "fadeOut", 99);
    const plan = planTransitions(capped, frames);
    expect(plan.videoFadeIn.get("l")).toBe(10);
    expect(plan.videoFadeOut.get("l")).toBe(25);
    expect(plan.audioFades.get("la")).toEqual({ in: 10, out: 25 });
    const merged = planTransitions(
      setFade(doc([t()]), "r", "fadeIn", 4),
      frames,
    );
    expect(merged.videoFadeIn.get("r")).toBe(10);
  });
  it("computes opacity at both edges", () => {
    const d = setFade(setFade(doc([]), "l", "fadeIn", 10), "l", "fadeOut", 5);
    const plan = planTransitions(d, frames),
      l = plan.clips.find((c) => c.id === "l")!;
    expect(clipOpacity(plan, l, 0)).toBe(0);
    expect(clipOpacity(plan, l, 5)).toBeCloseTo(0.5);
    expect(clipOpacity(plan, l, 12)).toBe(1);
    expect(clipOpacity(plan, l, 24)).toBe(0);
  });
  it("split keeps the fade-in on the left part and the fade-out on the right", () => {
    const d = setFade(setFade(doc([]), "l", "fadeIn", 5), "l", "fadeOut", 5);
    const next = split(d, "l", 10);
    const parts = next.clips
      .filter((c) => c.kind === "video" && c.layer === 0 && c.start < 25)
      .toSorted((a, b) => a.start - b.start);
    expect(parts.map((c) => [c.fadeIn ?? 0, c.fadeOut ?? 0])).toEqual([
      [5, 0],
      [0, 5],
    ]);
  });
});
