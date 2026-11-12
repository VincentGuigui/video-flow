import { describe, expect, it } from "vitest";
import { defaultTransform, type Clip, type Document } from "./model";
import { findWords, hitMarks, nextHit, normalize, searchHits } from "./search";
import type { Analysis } from "./transcript";

const words = (text: string, startS = 0) =>
  text.split(" ").map((t, i) => ({
    text: t,
    startUs: (startS + i) * 1_000_000,
    endUs: (startS + i + 0.8) * 1_000_000,
  }));

const clip = (id: string, over: Partial<Clip> = {}): Clip => ({
  id,
  kind: "video",
  assetId: "a",
  name: id,
  start: 0,
  sourceIn: 0,
  sourceOut: 250,
  layer: 0,
  enabled: true,
  linkId: null,
  gainDb: 0,
  transform: defaultTransform(),
  ...over,
});

const analyses: Record<string, Analysis> = {
  a: {
    summary: "",
    keywords: [],
    words: words("Hello world, the intro of the world"),
  },
  b: { summary: "", keywords: [], words: words("Another world here") },
};

describe("text search", () => {
  it("ignores case, accents and punctuation", () => {
    expect(normalize("  Été, déjà! ")).toBe("ete deja");
    expect(findWords("WORLD", words("Hello world, the world"))).toHaveLength(2);
    expect(findWords("ete", words("Cet été"))).toHaveLength(1);
  });
  it("matches consecutive words, the last one by its start", () => {
    const said = words("the intro of the introduction");
    expect(findWords("the intro", said).map((h) => h.startUs)).toEqual([
      0, 3_000_000,
    ]);
    expect(findWords("intro of", said)).toHaveLength(1);
    expect(findWords("   ", said)).toEqual([]);
  });
  it("places the occurrences in the assembly, inside the trimmed range only", () => {
    const doc: Document = {
      version: 1,
      clips: [
        // Source frames 25..150 at 25 fps: seconds 1 to 6.
        clip("v1", { sourceIn: 25, sourceOut: 150 }),
        clip("v2", { assetId: "b", start: 125, sourceOut: 75 }),
        clip("off", { assetId: "b", start: 200, enabled: false }),
        // A freeze frame shows a picture: nothing is said in it.
        clip("frozen", { start: 225, sourceOut: 50, stillFrame: 25 }),
      ],
    };
    const hits = searchHits(doc, analyses, "world", 25);
    // "world" at 1 s (offset 0) and 6 s (outside: source 150 is the out point);
    // "world" at 1 s of b in v2 → 125 + 25.
    expect(hits).toEqual([
      { clipId: "v1", frame: 0, offset: 0 },
      { clipId: "v2", frame: 150, offset: 25 },
    ]);
  });
  it("searches a linked pair once and marks both clips", () => {
    const doc: Document = {
      version: 1,
      clips: [
        clip("v", { linkId: "l" }),
        clip("s", { kind: "audio", linkId: "l", layer: 0 }),
      ],
    };
    const hits = searchHits(doc, analyses, "intro", 25);
    expect(hits).toEqual([{ clipId: "v", frame: 75, offset: 75 }]);
    expect(Object.fromEntries(hitMarks(doc, hits))).toEqual({
      v: [75],
      s: [75],
    });
  });
  it("moves to the next or previous occurrence, wrapping around", () => {
    const hits = [10, 50, 90].map((frame) => ({
      clipId: "c",
      frame,
      offset: 0,
    }));
    expect(nextHit(hits, 10)?.frame).toBe(50);
    expect(nextHit(hits, 95)?.frame).toBe(10);
    expect(nextHit(hits, 50, true)?.frame).toBe(10);
    expect(nextHit(hits, 5, true)?.frame).toBe(90);
    expect(nextHit([], 5)).toBeNull();
  });
});
