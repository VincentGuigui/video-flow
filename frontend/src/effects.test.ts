import { describe, expect, it } from "vitest";
import { defaultTransform, type Clip, type Document } from "./model";
import { EFFECTS } from "./effects";
import { cutKey, cuts } from "./transitions";

const clip = (
  id: string,
  start: number,
  kind: Clip["kind"] = "video",
  linkId: string | null = null,
  extra: Partial<Clip> = {},
): Clip => ({
  id,
  kind,
  linkId,
  assetId: id[0],
  name: id,
  start,
  sourceIn: 0,
  sourceOut: 25,
  layer: 0,
  enabled: true,
  gainDb: 0,
  transform: defaultTransform(),
  ...extra,
});
const doc = (clips: Clip[]): Document => ({
  version: 1,
  clips,
  transitions: [],
});
const effect = (id: string) => EFFECTS.find((e) => e.id === id)!;

describe("clip effects registry", () => {
  it("lists the effects that apply to each kind of clip", () => {
    const d = doc([
      clip("v", 0, "video", "p"),
      clip("va", 0, "audio", "p"),
      clip("m", 0, "audio"),
      clip("t", 0, "text"),
      clip("g", 25, "gap"),
    ]);
    const ids = (id: string) =>
      EFFECTS.filter((e) =>
        e.applies(
          d,
          d.clips.find((c) => c.id === id)!,
        ),
      ).map((e) => e.id);
    expect(ids("v")).toEqual(["fadeIn", "fadeOut", "speed", "zoom", "mute"]);
    expect(ids("m")).toEqual(["fadeIn", "fadeOut", "speed", "mute", "duck"]);
    expect(ids("t")).toEqual(["fadeIn", "fadeOut"]);
    expect(ids("g")).toEqual([]);
  });

  it("adds and removes a fade on the clip and its linked partner", () => {
    const d = doc([clip("v", 0, "video", "p"), clip("va", 0, "audio", "p")]);
    const fade = effect("fadeIn");
    expect(fade.active(d, d.clips[0])).toBe(false);
    const added = fade.add(d, d.clips[0], 30)!;
    expect(added.clips.map((c) => c.fadeIn)).toEqual([15, 15]);
    expect(fade.active(added, added.clips[0])).toBe(true);
    expect(fade.summary(added, added.clips[0], 30)).toBe("0.50 s");
    const removed = fade.remove(added, added.clips[0]);
    expect(removed.clips.map((c) => c.fadeIn)).toEqual([0, 0]);
  });

  it("removes speed, zooms, mute and duck ranges", () => {
    const ranges = [
      { start: 0, end: 5, gainDb: -60, ramp: 1, kind: "mute" as const },
      { start: 6, end: 9, gainDb: -15, ramp: 1, kind: "duck" as const },
    ];
    const d = doc([
      clip("v", 0, "video", "p", {
        speed: 2,
        zooms: [
          {
            start: 0,
            end: 10,
            scale: 2,
            x: 0.5,
            y: 0.5,
            easeIn: 1,
            easeOut: 1,
          },
        ],
      }),
      clip("va", 0, "audio", "p", { speed: 2, volumeRanges: ranges }),
    ]);
    const v = d.clips[0];
    expect(effect("speed").summary(d, v, 30)).toBe("200 %");
    expect(
      effect("speed")
        .remove(d, v)
        .clips.map((c) => c.speed ?? 1),
    ).toEqual([1, 1]);
    expect(effect("zoom").remove(d, v).clips[0].zooms).toEqual([]);
    expect(effect("mute").summary(d, v, 30)).toBe("1 range");
    const unmuted = effect("mute").remove(d, v);
    expect(unmuted.clips[1].volumeRanges).toEqual([ranges[1]]);
    expect(effect("speed").add(d, v, 30)).toBeNull();
  });
});

describe("cuts", () => {
  it("finds cuts between adjacent video clips on one lane, in order (not across an empty clip)", () => {
    const d = doc([
      clip("b", 25),
      clip("a", 0),
      clip("g", 50, "gap"),
      clip("c", 75),
      clip("x", 0, "audio"),
      clip("u", 0, "video", null, { layer: 1 }),
      clip("w", 25, "video", null, { layer: 1 }),
    ]);
    expect(cuts(d).map((c) => cutKey(c.leftId, c.rightId))).toEqual([
      "a>b",
      "u>w",
    ]);
  });
});
