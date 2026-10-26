import { describe, expect, it } from "vitest";
import {
  anchor,
  divergent,
  pickTake,
  stackedTakes,
  takeWords,
} from "./compare";
import { defaultTransform, type Clip, type Document } from "./model";

const c = (
  id: string,
  layer: number,
  kind: Clip["kind"] = "video",
  linkId: string | null = null,
  start = 0,
  enabled = true,
): Clip => ({
  id,
  kind,
  linkId,
  assetId: id,
  name: id,
  start,
  sourceIn: 0,
  sourceOut: 100,
  layer,
  enabled,
  gainDb: 0,
  transform: defaultTransform(),
});
const doc = (): Document => ({
  version: 1,
  clips: [
    c("t1", 0, "video", "p1"),
    c("t1a", 0, "audio", "p1"),
    c("t2", 1, "video", "p2", 0, false),
    c("t2a", 1, "audio", "p2", 0, false),
    c("t3", 2, "video", null, 20),
    c("later", 0, "video", null, 120),
  ],
});
const w = (text: string, s: number) => ({
  text,
  startUs: s * 1_000_000,
  endUs: s * 1_000_000 + 400_000,
});

describe("compare takes", () => {
  it("finds stacked takes including disabled ones, from video or audio", () => {
    expect(stackedTakes(doc(), "t1").map((t) => t.id)).toEqual([
      "t1",
      "t2",
      "t3",
    ]);
    expect(stackedTakes(doc(), "t1a").map((t) => t.id)).toEqual([
      "t1",
      "t2",
      "t3",
    ]);
    expect(stackedTakes(doc(), "later").map((t) => t.id)).toEqual(["later"]);
  });
  it("picking enables the take with its audio and disables the others", () => {
    const d = doc();
    const next = pickTake(d, stackedTakes(d, "t1"), "t2");
    const state = Object.fromEntries(next.clips.map((x) => [x.id, x.enabled]));
    expect(state).toEqual({
      t1: false,
      t1a: false,
      t2: true,
      t2a: true,
      t3: false,
      later: true,
    });
  });
  it("aligns on the first common word and flags words said in one take only", () => {
    const a = [w("Alors", 0), w("dans", 1), w("la", 2), w("boîte", 3)];
    const b = [w("euh", 5), w("dans", 6), w("la", 7), w("boite", 8)];
    expect(anchor([a, b])).toEqual({
      word: "dans",
      times: [1_000_000, 6_000_000],
    });
    expect(divergent([a, b])).toEqual([
      [true, false, false, false],
      [true, false, false, false],
    ]);
    expect(anchor([a, [w("autre", 1)]])).toBeNull();
    expect(
      anchor([
        [w("le", 0), w("câble", 1)],
        [w("euh", 0), w("le", 1), w("cable", 2)],
      ])?.word,
    ).toBe("câble");
    expect(anchor([[w("la", 0)], [w("la", 3)]])?.times).toEqual([0, 3_000_000]);
  });
  it("keeps only words inside the trimmed source range", () => {
    const clip = { ...c("x", 0), sourceIn: 25, sourceOut: 75 };
    expect(
      takeWords(clip, [w("a", 0.5), w("b", 1.5), w("c", 2.8)], 25).map(
        (x) => x.text,
      ),
    ).toEqual(["b"]);
  });
});
