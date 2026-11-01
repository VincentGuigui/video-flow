// Workspace zones: the zone last clicked receives Ctrl+A (select all) and Delete.
import {
  duration,
  layout,
  pack,
  remove,
  type Document,
  type Project,
} from "./model";

export type Zone = "media" | "timeline" | "flow" | "editor";

export const ZONE_LABELS: Record<Zone, string> = {
  media: "Project media",
  timeline: "Timeline",
  flow: "Clip flow",
  editor: "Editor",
};

// What Ctrl+A selects in a zone: assets for the media list, clips elsewhere.
export function zoneItems(
  zone: Zone,
  doc: Document,
  project: Project | null,
  frame: number,
): string[] {
  if (zone === "media") return project?.assets.map((a) => a.id) ?? [];
  if (zone === "flow")
    return doc.clips.filter((c) => c.kind !== "gap").map((c) => c.id);
  const placed = layout(doc).clips.filter((c) => c.kind !== "gap");
  if (zone === "timeline") return placed.map((c) => c.id);
  // Editor: the clips shown in the preview at the cursor.
  return placed
    .filter((c) => frame >= c.start && frame < c.start + duration(c))
    .map((c) => c.id);
}

// Lift (leave empty time) or ripple-delete several clips, linked partners included.
export function removeClips(
  doc: Document,
  ids: string[],
  ripple: boolean,
): Document {
  let next = pack(doc);
  for (const id of ids)
    if (next.clips.some((c) => c.id === id)) next = remove(next, id, ripple);
  return next;
}

// The edit without the clips of removed media; the time they took closes up.
export function withoutAssets(doc: Document, assetIds: string[]): Document {
  const gone = new Set(assetIds);
  return pack({
    ...doc,
    clips: doc.clips.filter((c) => !c.assetId || !gone.has(c.assetId)),
  });
}
