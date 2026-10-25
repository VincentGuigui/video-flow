import { describe, it, expect } from "vitest";
import {
  defaultTransform,
  detach,
  duration,
  keyboardStep,
  layout,
  move,
  partners,
  remove,
  resize,
  split,
  trim,
  zoomAt,
  type Clip,
  type Document,
  type Settings,
} from "./model";

const c = (
  id: string,
  start = 0,
  kind: Clip["kind"] = "video",
  linkId: string | null = null,
): Clip => ({
  id,
  kind,
  linkId,
  assetId: "asset",
  name: id,
  start,
  sourceIn: 10,
  sourceOut: 110,
  layer: 0,
  enabled: true,
  gainDb: 0,
  transform: defaultTransform(),
});
const document = (): Document => ({
  version: 1,
  clips: [
    c("v", 0, "video", "pair"),
    c("a", 0, "audio", "pair"),
    c("next", 100),
  ],
});
describe("linked editing", () => {
  it("splits both media at one frame and creates two independent linked pairs", () => {
    const doc = split(document(), "a", 40);
    expect(doc.clips).toHaveLength(5);
    const left = partners(doc, "v"),
      right = doc.clips.filter((c) => c.start === 40);
    expect(left).toHaveLength(2);
    expect(right).toHaveLength(2);
    expect(left[0].linkId).not.toBe(right[0].linkId);
    expect(left.map((c) => c.sourceOut)).toEqual([50, 50]);
    expect(right.map((c) => c.sourceIn)).toEqual([50, 50]);
    expect(layout(doc).total).toBe(200);
  });
  it("detaches without changing timing and moves independently afterwards", () => {
    const doc = move(detach(document(), "v"), "a", 20, 2);
    expect(doc.clips.find((c) => c.id === "v")!.start).toBe(0);
    expect(doc.clips.find((c) => c.id === "a")!.start).toBe(20);
    expect(doc.clips.find((c) => c.id === "a")!.layer).toBe(2);
    expect(partners(doc, "a")).toHaveLength(1);
  });
  it("lift preserves time using an explicit empty clip", () => {
    const doc = remove(document(), "v", false);
    expect(layout(doc).total).toBe(200);
    expect(doc.clips.map((c) => c.kind).sort()).toEqual(["gap", "video"]);
    expect(doc.clips.find((c) => c.id === "next")!.start).toBe(100);
  });
  it("backspace ripples uncovered time and removes the linked pair", () => {
    const doc = remove(document(), "a", true);
    expect(layout(doc).total).toBe(100);
    expect(doc.clips).toHaveLength(1);
    expect(doc.clips[0].start).toBe(0);
  });
  it("does not remove time still covered by another layer", () => {
    const doc = document();
    doc.clips.push({ ...c("overlay"), layer: 1 });
    const result = remove(doc, "v", true);
    expect(layout(result).total).toBe(200);
    expect(result.clips.find((c) => c.id === "next")!.start).toBe(100);
  });
});
describe("trim modes", () => {
  it("extends source through both bottom handles and merges neighboring empty clips", () => {
    let doc = trim(document(), "v", "out", -10, false, 400);
    doc = trim(doc, "v", "out", -10, false, 400);
    expect(doc.clips.filter((c) => c.kind === "gap")).toHaveLength(1);
    expect(duration(doc.clips.find((c) => c.kind === "gap")!)).toBe(20);
    doc = trim(doc, "v", "out", 30, false, 400);
    expect(doc.clips.find((c) => c.id === "v")!.sourceOut).toBe(120);
    expect(doc.clips.find((c) => c.id === "next")!.start).toBe(110);
    expect(layout(doc).total).toBe(210);
    const head = trim(document(), "v", "in", -10, false, 400);
    expect(head.clips.find((c) => c.id === "v")!.sourceIn).toBe(0);
    expect(head.clips.find((c) => c.id === "next")!.start).toBe(110);
    expect(layout(head).total).toBe(210);
  });
  it("top tail reduces duration and ripples later clips", () => {
    const doc = trim(document(), "v", "out", -20, true, 400);
    expect(layout(doc).total).toBe(180);
    expect(partners(doc, "v").map((c) => duration(c))).toEqual([80, 80]);
    expect(doc.clips.find((c) => c.id === "next")!.start).toBe(80);
  });
  it("bottom tail creates an empty clip and keeps duration", () => {
    const doc = trim(document(), "v", "out", -20, false, 400);
    expect(layout(doc).total).toBe(200);
    expect(doc.clips.find((c) => c.kind === "gap")?.start).toBe(80);
    expect(duration(doc.clips.find((c) => c.kind === "gap")!)).toBe(20);
  });
  it("bottom extension consumes its neighboring empty clip", () => {
    const doc = trim(
      trim(document(), "v", "out", -20, false, 400),
      "v",
      "out",
      20,
      false,
      400,
    );
    expect(layout(doc).total).toBe(200);
    expect(doc.clips.some((c) => c.kind === "gap")).toBe(false);
    expect(doc.clips.find((c) => c.id === "v")!.sourceOut).toBe(110);
  });
  it("bottom head creates leading space and can consume it again", () => {
    const doc = trim(document(), "v", "in", 20, false, 400);
    expect(layout(doc).total).toBe(200);
    expect(doc.clips.find((c) => c.id === "v")!.start).toBe(20);
    const restored = trim(doc, "v", "in", -20, false, 400);
    expect(restored.clips.some((c) => c.kind === "gap")).toBe(false);
    expect(restored.clips.find((c) => c.id === "v")!.start).toBe(0);
  });
  it("never extends past source bounds or trims below one frame", () => {
    expect(
      trim(document(), "v", "out", 500, true, 130).clips.find(
        (c) => c.id === "v",
      )!.sourceOut,
    ).toBe(130);
    expect(
      trim(document(), "v", "in", -999, true, 400).clips.find(
        (c) => c.id === "v",
      )!.sourceIn,
    ).toBe(0);
    expect(
      duration(
        trim(document(), "v", "in", 999, true, 400).clips.find(
          (c) => c.id === "v",
        )!,
      ),
    ).toBe(1);
  });
});
it("fits the old canvas in a different ratio without stretching or changing crops", () => {
  const settings: Settings = {
    width: 1920,
    height: 1080,
    frameRate: { num: 30, den: 1 },
  };
  const original = document();
  original.clips[0].transform.cropLeft = 0.1;
  const doc = resize(original, settings, 1080, 1920),
    t = doc.clips[0].transform;
  expect(t.width).toBe(1080);
  expect(t.height).toBe(607.5);
  expect(t.x).toBe(0);
  expect(t.y).toBe(656.25);
  expect(t.cropLeft).toBe(0.1);
});
it("keeps the hovered time under the pointer when zoom changes", () => {
  const old = 2,
    next = 5,
    scroll = 200,
    pointer = 120;
  expect((zoomAt(old, next, scroll, pointer) + pointer) / next).toBe(
    (scroll + pointer) / old,
  );
});
it("uses frame, second, ten-second and boundary keyboard steps", () => {
  expect(keyboardStep("ArrowRight", false, false, 30)).toBe(1);
  expect(keyboardStep("ArrowLeft", true, false, 30)).toBe(-30);
  expect(keyboardStep("ArrowRight", false, true, 30000 / 1001)).toBe(300);
  expect(keyboardStep("ArrowLeft", true, true, 30)).toBe("start");
  expect(keyboardStep("End", false, false, 30)).toBe("end");
});
