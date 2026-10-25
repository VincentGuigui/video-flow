export interface Transform {
  x: number;
  y: number;
  width: number;
  height: number;
  cropLeft: number;
  cropRight: number;
  cropTop: number;
  cropBottom: number;
}
export interface Clip {
  id: string;
  kind: "video" | "audio" | "gap";
  assetId: string | null;
  name: string;
  start: number;
  sourceIn: number;
  sourceOut: number;
  layer: number;
  enabled: boolean;
  linkId: string | null;
  gainDb: number;
  transform: Transform;
}
export interface Document {
  version: 1;
  clips: Clip[];
}
export interface Asset {
  id: string;
  path: string;
  probe: {
    durationUs: number;
    video: null | { width: number; height: number };
    audioStreams: unknown[];
  };
}
export interface Settings {
  width: number;
  height: number;
  frameRate: { num: number; den: number };
  [key: string]: unknown;
}
export interface Project {
  id: string;
  name: string;
  revision: number;
  settings: Settings;
  assets: Asset[];
}
export const uid = () => crypto.randomUUID();
export const duration = (c: Clip) => c.sourceOut - c.sourceIn;
export const clone = <T>(value: T): T => structuredClone(value);
export const fps = (s: Settings) => s.frameRate.num / s.frameRate.den;
export const defaultTransform = (): Transform => ({
  x: 0,
  y: 0,
  width: 1920,
  height: 1080,
  cropLeft: 0,
  cropRight: 0,
  cropTop: 0,
  cropBottom: 0,
});

export function layout(doc: Document): {
  clips: Clip[];
  total: number;
  position: (frame: number) => number;
} {
  const intervals: number[][] = [];
  for (const c of doc.clips
    .filter((c) => c.enabled)
    .toSorted((a, b) => a.start - b.start)) {
    const end = c.start + duration(c),
      last = intervals.at(-1);
    if (last && c.start <= last[1]) last[1] = Math.max(last[1], end);
    else intervals.push([c.start, end]);
  }
  const position = (f: number) =>
    intervals.reduce((n, [a, b]) => n + Math.max(0, Math.min(f, b) - a), 0);
  return {
    clips: doc.clips
      .filter((c) => c.enabled)
      .map((c) => ({ ...c, start: position(c.start) })),
    total: intervals.reduce((n, [a, b]) => n + b - a, 0),
    position,
  };
}
// Pack only unintended empty time. Disabled alternatives remain visible at their slot.
export function pack(doc: Document): Document {
  const { position } = layout(doc);
  return {
    ...doc,
    clips: doc.clips.map((c) => ({ ...c, start: position(c.start) })),
  };
}
export function partners(doc: Document, id: string): Clip[] {
  const c = doc.clips.find((c) => c.id === id);
  return c
    ? doc.clips.filter(
        (p) => p.id === id || (!!c.linkId && p.linkId === c.linkId),
      )
    : [];
}
export function split(doc: Document, id: string, frame: number): Document {
  const selected = partners(doc, id),
    c = selected[0];
  if (!c || frame <= c.start || frame >= c.start + duration(c)) return doc;
  const result = clone(doc),
    ids = new Set(selected.map((c) => c.id));
  const leftLink = c.linkId ? uid() : null,
    rightLink = c.linkId ? uid() : null;
  result.clips = result.clips.flatMap((p) => {
    if (!ids.has(p.id)) return [p];
    const boundary = p.sourceIn + frame - p.start;
    return [
      { ...p, sourceOut: boundary, linkId: leftLink },
      {
        ...clone(p),
        id: uid(),
        start: frame,
        sourceIn: boundary,
        linkId: rightLink,
      },
    ];
  });
  return result;
}
export function detach(doc: Document, id: string): Document {
  const ids = new Set(partners(doc, id).map((c) => c.id));
  return {
    ...doc,
    clips: doc.clips.map((c) => (ids.has(c.id) ? { ...c, linkId: null } : c)),
  };
}
function gap(start: number, length: number, layer: number): Clip {
  return {
    id: uid(),
    kind: "gap",
    assetId: null,
    name: "Empty clip",
    start,
    sourceIn: 0,
    sourceOut: length,
    layer,
    enabled: true,
    linkId: null,
    gainDb: 0,
    transform: defaultTransform(),
  };
}
export function remove(doc: Document, id: string, ripple: boolean): Document {
  const selected = partners(doc, id),
    c = selected[0];
  if (!c) return doc;
  const ids = new Set(selected.map((c) => c.id)),
    end = c.start + duration(c);
  let clips = doc.clips.filter((c) => !ids.has(c.id));
  // An overlapping layer still occupies this time. Only uncovered time ripples away.
  if (!ripple) clips.push(gap(c.start, duration(c), c.layer));
  return ripple ? pack({ ...doc, clips }) : { ...doc, clips };
}
export function move(
  doc: Document,
  id: string,
  start: number,
  layer: number,
): Document {
  const selected = partners(doc, id),
    ids = new Set(selected.map((c) => c.id));
  return pack({
    ...doc,
    clips: doc.clips.map((c) =>
      ids.has(c.id)
        ? {
            ...c,
            start: Math.max(0, Math.round(start)),
            layer: Math.max(0, layer),
          }
        : c,
    ),
  });
}
export function trim(
  doc: Document,
  id: string,
  edge: "in" | "out",
  delta: number,
  ripple: boolean,
  maxFrames: number,
): Document {
  const selected = partners(doc, id),
    c = selected[0];
  if (!c) return doc;
  const d = duration(c),
    ids = new Set(selected.map((c) => c.id));
  delta = Math.round(delta);
  delta =
    edge === "in"
      ? Math.max(-c.sourceIn, Math.min(d - 1, delta))
      : Math.max(1 - d, Math.min(maxFrames - c.sourceOut, delta));
  if (!delta) return doc;
  const next = clone(doc);
  const end = c.start + d;
  if (edge === "in") {
    if (ripple) {
      // Move later assembly time by the exact source delta; the selected head stays put.
      next.clips = next.clips.map((p) =>
        ids.has(p.id)
          ? { ...p, sourceIn: p.sourceIn + delta }
          : p.start >= end
            ? { ...p, start: Math.max(0, p.start - delta) }
            : p,
      );
    } else {
      if (delta < 0) {
        const available = c.start;
        delta = Math.max(delta, -available);
        // Consume empty space behind the handle. Do not overwrite occupied preceding media.
        const preceding = next.clips.filter(
          (p) =>
            !ids.has(p.id) &&
            p.enabled &&
            p.kind !== "gap" &&
            p.layer === c.layer &&
            p.start < c.start,
        );
        const previousEnd = Math.max(
          0,
          ...preceding.map((p) => p.start + duration(p)),
        );
        delta = Math.max(delta, previousEnd - c.start);
      }
      next.clips = next.clips.map((p) =>
        ids.has(p.id)
          ? { ...p, sourceIn: p.sourceIn + delta, start: p.start + delta }
          : p,
      );
      if (delta > 0) next.clips.push(gap(c.start, delta, c.layer));
      else consumeGaps(next, c.start + delta, c.start, c.layer);
    }
  } else {
    next.clips = next.clips.map((p) =>
      ids.has(p.id)
        ? { ...p, sourceOut: p.sourceOut + delta }
        : ripple && p.start >= end
          ? { ...p, start: Math.max(0, p.start + delta) }
          : p,
    );
    if (!ripple) {
      if (delta < 0) next.clips.push(gap(end + delta, -delta, c.layer));
      else {
        // Extend only into neighboring explicit gaps; clip at the next occupied source.
        const nextStart = Math.min(
          Infinity,
          ...next.clips
            .filter(
              (p) =>
                !ids.has(p.id) &&
                p.enabled &&
                p.kind !== "gap" &&
                p.layer === c.layer &&
                p.start >= end,
            )
            .map((p) => p.start),
        );
        const bounded = Math.min(delta, nextStart - end);
        next.clips = next.clips.map((p) =>
          ids.has(p.id)
            ? { ...p, sourceOut: p.sourceOut - delta + bounded }
            : p,
        );
        consumeGaps(next, end, end + bounded, c.layer);
      }
    }
  }
  return ripple ? pack(next) : next;
}
function consumeGaps(doc: Document, a: number, b: number, layer: number) {
  doc.clips = doc.clips.flatMap((c) => {
    if (
      c.kind !== "gap" ||
      c.layer !== layer ||
      c.start >= b ||
      c.start + duration(c) <= a
    )
      return [c];
    const end = c.start + duration(c),
      parts: Clip[] = [];
    if (c.start < a) parts.push(gap(c.start, a - c.start, c.layer));
    if (end > b) parts.push(gap(b, end - b, c.layer));
    return parts;
  });
}
export function resize(
  doc: Document,
  old: Settings,
  width: number,
  height: number,
): Document {
  const scale = Math.min(width / old.width, height / old.height),
    dx = (width - old.width * scale) / 2,
    dy = (height - old.height * scale) / 2;
  return {
    ...doc,
    clips: doc.clips.map((c) => ({
      ...c,
      transform: {
        ...c.transform,
        x: c.transform.x * scale + dx,
        y: c.transform.y * scale + dy,
        width: c.transform.width * scale,
        height: c.transform.height * scale,
      },
    })),
  };
}
export const timecode = (f: number, rate: number) => {
  const n = Math.max(1, Math.round(rate));
  const ff = Math.max(0, Math.round(f));
  return [
    Math.floor(ff / n / 3600),
    Math.floor(ff / n / 60) % 60,
    Math.floor(ff / n) % 60,
    ff % n,
  ]
    .map((v) => String(v).padStart(2, "0"))
    .join(":");
};
export function zoomAt(
  old: number,
  next: number,
  scroll: number,
  pointer: number,
) {
  return ((scroll + pointer) * next) / old - pointer;
}
export function keyboardStep(
  key: string,
  shift: boolean,
  ctrl: boolean,
  rate: number,
): number | "start" | "end" | null {
  if (key === "Home" || (key === "ArrowLeft" && ctrl && shift)) return "start";
  if (key === "End" || (key === "ArrowRight" && ctrl && shift)) return "end";
  if (key === "ArrowLeft" || key === "ArrowRight")
    return (
      (key === "ArrowLeft" ? -1 : 1) *
      (ctrl ? Math.round(rate * 10) : shift ? Math.round(rate) : 1)
    );
  return null;
}
