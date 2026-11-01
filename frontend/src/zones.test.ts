import { describe, expect, it } from "vitest";
import {
  defaultTransform,
  type Clip,
  type Document,
  type Project,
} from "./model";
import { removeClips, withoutAssets, zoneItems } from "./zones";

const clip = (
  id: string,
  kind: Clip["kind"],
  start: number,
  asset: string | null = id,
  link: string | null = null,
): Clip => ({
  id,
  kind,
  assetId: kind === "gap" ? null : asset,
  name: id,
  start,
  sourceIn: 0,
  sourceOut: 50,
  layer: 0,
  enabled: true,
  linkId: link,
  gainDb: 0,
  transform: defaultTransform(),
});

const doc: Document = {
  version: 1,
  clips: [
    clip("v1", "video", 0, "a", "p"),
    clip("a1", "audio", 0, "a", "p"),
    clip("v2", "video", 50, "b"),
    clip("g", "gap", 100),
    clip("v3", "video", 150, "a"),
  ],
};
const project = {
  assets: [{ id: "a" }, { id: "b" }],
} as unknown as Project;

describe("workspace zones", () => {
  it("selects the items of each zone", () => {
    expect(zoneItems("media", doc, project, 0)).toEqual(["a", "b"]);
    expect(zoneItems("flow", doc, project, 0)).toEqual([
      "v1",
      "a1",
      "v2",
      "v3",
    ]);
    expect(zoneItems("timeline", doc, project, 0)).toHaveLength(4);
    expect(zoneItems("editor", doc, project, 60)).toEqual(["v2"]);
  });
  it("removes several clips with their partners, lifted or rippled", () => {
    const lifted = removeClips(doc, ["v1", "a1", "v2"], false);
    expect(
      lifted.clips.filter((c) => c.kind !== "gap").map((c) => c.id),
    ).toEqual(["v3"]);
    const rippled = removeClips(doc, ["v1", "v2"], true);
    expect(rippled.clips.find((c) => c.id === "v3")!.start).toBeLessThan(150);
    expect(rippled.clips.some((c) => c.id === "a1")).toBe(false);
  });
  it("drops the clips of removed media and closes the time", () => {
    const next = withoutAssets(doc, ["a"]);
    expect(next.clips.map((c) => c.id)).toEqual(["v2", "g"]);
    expect(next.clips[0].start).toBe(0);
  });
});
