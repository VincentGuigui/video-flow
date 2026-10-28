import { describe, expect, it } from "vitest";
import {
  defaultTransform,
  move,
  setSpeed,
  trim,
  type Clip,
  type Document,
} from "./model";
import { addTitle, setTitle, titleUrl } from "./titles";
import { clipOpacity, planTransitions } from "./transitions";

const video = (id: string, start: number, layer = 0): Clip => ({
  id,
  kind: "video",
  assetId: id,
  name: id,
  start,
  sourceIn: 0,
  sourceOut: 100,
  layer,
  enabled: true,
  linkId: null,
  gainDb: 0,
  transform: defaultTransform(),
});

describe("text clips", () => {
  const base: Document = { version: 1, clips: [video("v", 0)] };

  it("adds a title above the picture at the cursor", () => {
    const { doc, id } = addTitle(base, "title", 20, 25);
    const title = doc.clips.find((c) => c.id === id)!;
    expect(title).toMatchObject({
      kind: "text",
      assetId: null,
      start: 20,
      layer: 1,
      sourceIn: 0,
      sourceOut: 75,
      name: "Title",
    });
    expect(title.title).toMatchObject({ style: "title", box: false });
    const lower = addTitle(doc, "lower_third", 30, 25);
    const third = lower.doc.clips.find((c) => c.id === lower.id)!;
    expect(third.layer).toBe(2); // above the title it overlaps
    expect(third.title).toMatchObject({ style: "lower_third", box: true });
    expect(third.name).toBe("Name");
  });

  it("shares video lanes: moving onto a picture opens a new lane", () => {
    const { doc, id } = addTitle(base, "title", 150, 25);
    expect(doc.clips.find((c) => c.id === id)!.layer).toBe(0);
    const moved = move(doc, id, 10, 0);
    expect(moved.clips.find((c) => c.id === id)!.layer).toBe(1);
  });

  it("edits text and renames the clip", () => {
    const { doc, id } = addTitle(base, "lower_third", 0, 25);
    const next = setTitle(doc, id, { text: "\nAda Lovelace\nMathematician" });
    const clip = next.clips.find((c) => c.id === id)!;
    expect(clip.name).toBe("Ada Lovelace");
    expect(clip.title!.text).toBe("\nAda Lovelace\nMathematician");
    const spec = new URL(titleUrl(clip.title!), "http://x").searchParams;
    expect(JSON.parse(spec.get("spec")!)).toEqual(clip.title);
  });

  it("extends from the head without a source and keeps normal speed", () => {
    const { doc, id } = addTitle(
      { version: 1, clips: [video("v", 0), video("w", 100)] },
      "title",
      100,
      25,
    );
    const longer = trim(doc, id, "in", -20, false, 1e9);
    const clip = longer.clips.find((c) => c.id === id)!;
    expect(clip).toMatchObject({ start: 80, sourceIn: 0, sourceOut: 95 });
    expect(setSpeed(longer, id, 2)).toBe(longer);
  });

  it("fades like a picture", () => {
    const { doc, id } = addTitle(base, "title", 0, 25);
    const faded: Document = {
      ...doc,
      clips: doc.clips.map((c) => (c.id === id ? { ...c, fadeIn: 10 } : c)),
    };
    const plan = planTransitions(faded, () => 1000);
    const clip = plan.clips.find((c) => c.id === id)!;
    expect(clipOpacity(plan, clip, 5)).toBeCloseTo(0.5);
    expect(clipOpacity(plan, clip, 20)).toBe(1);
  });
});
