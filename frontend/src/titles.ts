// Text clips (spec 21). The backend draws them (backend/videoflow/editor/titles.py); the
// preview shows the same picture from /api/title.
import { defaultTransform, move, uid, type Clip, type Document } from "./model";

export interface Title {
  text: string; // lines separated by newlines
  style: "title" | "lower_third";
  size: number; // first line's font size, relative to the picture height
  color: string;
  box: boolean;
  boxColor: string;
  boxOpacity: number;
}

export const TITLE_PRESETS: Record<
  Title["style"],
  { title: Title; seconds: number }
> = {
  title: {
    title: {
      text: "Title",
      style: "title",
      size: 0.08,
      color: "#ffffff",
      box: false,
      boxColor: "#000000",
      boxOpacity: 0.75,
    },
    seconds: 3,
  },
  lower_third: {
    title: {
      text: "Name\nRole",
      style: "lower_third",
      size: 0.05,
      color: "#ffffff",
      box: true,
      boxColor: "#1d3557",
      boxOpacity: 0.85,
    },
    seconds: 5,
  },
};

export const titleName = (title: Title) =>
  title.text
    .split("\n")
    .find((line) => line.trim())
    ?.trim() ?? "Title";

export const titleUrl = (title: Title) =>
  `/api/title?spec=${encodeURIComponent(JSON.stringify(title))}`;

// A text clip at `frame`, on the lane above every picture it covers.
export function addTitle(
  doc: Document,
  style: Title["style"],
  frame: number,
  rate: number,
): { doc: Document; id: string } {
  const preset = TITLE_PRESETS[style],
    length = Math.max(1, Math.round(preset.seconds * rate));
  const below = doc.clips.filter(
    (c) =>
      c.enabled &&
      c.kind !== "audio" &&
      c.kind !== "gap" &&
      c.start < frame + length &&
      c.start + (c.sourceOut - c.sourceIn) / (c.speed ?? 1) > frame,
  );
  const clip: Clip = {
    id: uid(),
    kind: "text",
    assetId: null,
    name: titleName(preset.title),
    start: frame,
    sourceIn: 0,
    sourceOut: length,
    layer: 0,
    enabled: true,
    linkId: null,
    gainDb: 0,
    transform: defaultTransform(),
    title: { ...preset.title },
  };
  const layer = Math.max(-1, ...below.map((c) => c.layer)) + 1;
  return {
    doc: move({ ...doc, clips: [...doc.clips, clip] }, clip.id, frame, layer),
    id: clip.id,
  };
}

export function setTitle(
  doc: Document,
  id: string,
  update: Partial<Title>,
): Document {
  return {
    ...doc,
    clips: doc.clips.map((c) => {
      if (c.id !== id || !c.title) return c;
      const title = { ...c.title, ...update };
      return { ...c, title, name: titleName(title) };
    }),
  };
}
