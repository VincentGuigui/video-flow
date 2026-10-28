import type { Transition } from "./transitions";
import type { Zoom } from "./zoom";
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
  fitMode?: "fit" | "fill";
  heldRange?: { start: number; end: number } | null;
  speed?: number; // 1 = normal; source frames per timeline frame
  zooms?: Zoom[];
  fadeIn?: number; // frames, edge fade at the clip's start (spec 21)
  fadeOut?: number;
  background?: { mode: "transparent" | "color" | "blur"; color: string };
  resizeReference?: { width: number; height: number; transform: Transform };
}
export interface Document {
  version: 1;
  clips: Clip[];
  transitions?: Transition[];
}
export interface Asset {
  id: string;
  path: string;
  probe: {
    durationUs: number;
    video: null | { width: number; height: number; rotation?: number };
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
// Speed (spec 21): source frames per timeline frame; timeline length is span / speed.
export const speedOf = (c: Clip) => c.speed ?? 1;
export const span = (c: Clip) => c.sourceOut - c.sourceIn;
export const duration = (c: Clip) =>
  speedOf(c) === 1 ? span(c) : Math.max(1, Math.round(span(c) / speedOf(c)));
// Source frames covered by `frames` of timeline, and the reverse (rounded down).
export const toSource = (c: Clip, frames: number) =>
  speedOf(c) === 1 ? frames : Math.round(frames * speedOf(c));
export const toTimeline = (c: Clip, frames: number) =>
  speedOf(c) === 1 ? frames : Math.floor(frames / speedOf(c));
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
    .toSorted((a, b) => occupied(a)[0] - occupied(b)[0])) {
    const [start, end] = occupied(c),
      last = intervals.at(-1);
    if (last && start <= last[1]) last[1] = Math.max(last[1], end);
    else intervals.push([start, end]);
  }
  const prefix = [0];
  for (const [a, b] of intervals) prefix.push(prefix.at(-1)! + b - a);
  const position = (f: number) => {
    let low = 0,
      high = intervals.length;
    while (low < high) {
      const middle = (low + high) >>> 1;
      if (intervals[middle][0] <= f) low = middle + 1;
      else high = middle;
    }
    const index = low - 1;
    return index < 0
      ? 0
      : prefix[index] + Math.min(f, intervals[index][1]) - intervals[index][0];
  };
  return {
    clips: doc.clips
      .filter((c) => c.enabled)
      .map((c) => ({ ...c, start: position(c.start) })),
    total: prefix.at(-1)!,
    position,
  };
}
export function occupied(c: Clip): [number, number] {
  return [
    Math.min(c.start, c.heldRange?.start ?? c.start),
    Math.max(c.start + duration(c), c.heldRange?.end ?? 0),
  ];
}
// Pack only unintended empty time. Disabled alternatives remain visible at their slot.
export function pack(doc: Document): Document {
  const { position } = layout(doc);
  return {
    ...doc,
    clips: doc.clips.map((c) => ({
      ...c,
      start:
        c.heldRange && !c.enabled
          ? position(c.heldRange.start) + c.start - c.heldRange.start
          : position(c.start),
      heldRange: c.heldRange
        ? c.enabled
          ? {
              start: position(c.heldRange.start),
              end: position(c.heldRange.end),
            }
          : {
              start: position(c.heldRange.start),
              end:
                position(c.heldRange.start) +
                c.heldRange.end -
                c.heldRange.start,
            }
        : c.heldRange,
    })),
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
    ids = new Set(selected.map((c) => c.id)),
    rightIds = new Map<string, string>();
  const leftLink = c.linkId ? uid() : null,
    rightLink = c.linkId ? uid() : null;
  result.clips = result.clips.flatMap((p) => {
    if (!ids.has(p.id)) return [p];
    const boundary = p.sourceIn + toSource(p, frame - p.start);
    return [
      {
        ...p,
        sourceOut: boundary,
        linkId: leftLink,
        fadeOut: 0,
        heldRange: p.heldRange
          ? { start: Math.min(p.heldRange.start, p.start), end: frame }
          : null,
      },
      {
        ...clone(p),
        id: rightIds.set(p.id, uid()).get(p.id)!,
        start: frame,
        sourceIn: boundary,
        linkId: rightLink,
        fadeIn: 0,
        heldRange: p.heldRange
          ? {
              start: frame,
              end: Math.max(p.heldRange.end, p.start + duration(p)),
            }
          : null,
      },
    ];
  });
  // The outgoing transition stays on the cut that follows the right part.
  result.transitions = result.transitions?.map((t) =>
    rightIds.has(t.leftId) ? { ...t, leftId: rightIds.get(t.leftId)! } : t,
  );
  return result;
}
export function linkCandidates(doc: Document, id: string): Clip[] {
  const clip = doc.clips.find((c) => c.id === id);
  if (!clip || clip.linkId || clip.kind === "gap") return [];
  return doc.clips.filter(
    (c) =>
      !c.linkId &&
      c.kind !== "gap" &&
      c.kind !== clip.kind &&
      c.start === clip.start &&
      duration(c) === duration(clip),
  );
}
export function linkClips(
  doc: Document,
  id: string,
  otherId: string,
): Document {
  const clip = doc.clips.find((c) => c.id === id);
  if (!clip || !linkCandidates(doc, id).some((c) => c.id === otherId))
    throw Error(
      "Align the video and audio start and duration before linking them",
    );
  const linkId = uid();
  const next = {
    ...doc,
    clips: doc.clips.map((c) =>
      c.id === id || c.id === otherId ? { ...c, linkId } : c,
    ),
  };
  return move(next, id, clip.start, clip.layer);
}
export function trimAudio(
  doc: Document,
  id: string,
  edge: "in" | "out",
  delta: number,
  maxFrames: number,
): Document {
  const selected = partners(doc, id),
    c = doc.clips.find((c) => c.id === id);
  if (!c) return doc;
  delta = Math.round(delta);
  delta =
    edge === "in"
      ? Math.max(
          -Math.min(c.start, ...selected.map((p) => toTimeline(p, p.sourceIn))),
          Math.min(duration(c) - 1, delta),
        )
      : Math.max(
          1 - duration(c),
          Math.min(toTimeline(c, maxFrames - c.sourceOut), delta),
        );
  if (!delta) return doc;
  const ids = new Set(selected.map((c) => c.id));
  const [start, end] = occupied(c);
  return {
    ...doc,
    clips: doc.clips.map((p) =>
      ids.has(p.id)
        ? {
            ...p,
            sourceIn: p.sourceIn + (edge === "in" ? toSource(p, delta) : 0),
            sourceOut: p.sourceOut + (edge === "out" ? toSource(p, delta) : 0),
            start: p.start + (edge === "in" ? delta : 0),
            heldRange: p.id === id ? { start, end } : p.heldRange,
          }
        : p,
    ),
  };
}
export function detach(doc: Document, id: string): Document {
  const ids = new Set(partners(doc, id).map((c) => c.id));
  return {
    ...doc,
    clips: doc.clips.map((c) => (ids.has(c.id) ? { ...c, linkId: null } : c)),
  };
}
// A video clip can get its own source audio back unless it is already linked to it.
export function canRestoreAudio(
  doc: Document,
  id: string,
  asset?: Asset,
): boolean {
  const clip = doc.clips.find((c) => c.id === id);
  if (!clip || clip.kind !== "video" || !asset?.probe.audioStreams.length)
    return false;
  return !partners(doc, id).some(
    (p) =>
      p.kind === "audio" &&
      p.assetId === clip.assetId &&
      p.sourceIn === clip.sourceIn &&
      p.sourceOut === clip.sourceOut,
  );
}
// Re-create the video's original audio, linked and aligned. Other audio clips are
// left in place; a different audio linked to the video becomes independent.
export function restoreAudio(doc: Document, id: string): Document {
  const video = doc.clips.find((c) => c.id === id);
  if (!video || video.kind !== "video") return doc;
  const linkId = uid();
  const audio: Clip = {
    id: uid(),
    kind: "audio",
    assetId: video.assetId,
    name: video.name,
    start: video.start,
    sourceIn: video.sourceIn,
    sourceOut: video.sourceOut,
    layer: video.layer,
    enabled: true,
    linkId,
    gainDb: 0,
    transform: defaultTransform(),
  };
  const next = detach(doc, id);
  next.clips = [
    ...next.clips.map((c) => (c.id === id ? { ...c, linkId } : c)),
    audio,
  ];
  return move(next, id, video.start, video.layer);
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
  if (!ripple) {
    const [start, end] = occupied(c);
    const ranges = selected.map(occupied);
    const a = Math.min(start, ...ranges.map((r) => r[0])),
      b = Math.max(end, ...ranges.map((r) => r[1]));
    clips.push(gap(a, b - a, c.layer));
  }
  return ripple ? pack({ ...doc, clips }) : mergeGaps({ ...doc, clips });
}
export function move(
  doc: Document,
  id: string,
  start: number,
  layer: number,
): Document {
  const selected = partners(doc, id),
    ids = new Set(selected.map((c) => c.id));
  start = Math.max(0, Math.round(start));
  layer = Math.max(0, Math.min(999, layer));
  // Moving into occupied time creates a visible parallel lane instead of
  // obscuring two draggable blocks on the same lane.
  while (
    layer < 1000 &&
    doc.clips.some(
      (other) =>
        !ids.has(other.id) &&
        other.enabled &&
        other.layer === layer &&
        selected.some(
          (c) =>
            c.kind === other.kind &&
            start < other.start + duration(other) &&
            start + duration(c) > other.start,
        ),
    )
  )
    layer++;
  if (layer > 999) return doc;
  return pack({
    ...doc,
    clips: doc.clips.map((c) =>
      ids.has(c.id)
        ? {
            ...c,
            start: Math.max(0, Math.round(start)),
            layer: Math.max(0, layer),
            heldRange: c.heldRange
              ? {
                  start: Math.max(0, c.heldRange.start + start - c.start),
                  end: c.heldRange.end + start - c.start,
                }
              : null,
          }
        : c,
    ),
  });
}
function shifted(clip: Clip, delta: number): Clip {
  const start = Math.max(0, clip.start + delta),
    change = start - clip.start;
  return {
    ...clip,
    start,
    heldRange: clip.heldRange
      ? {
          start: Math.max(0, clip.heldRange.start + change),
          end: clip.heldRange.end + change,
        }
      : clip.heldRange,
  };
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
    c = doc.clips.find((c) => c.id === id);
  if (!c) return doc;
  const d = duration(c),
    ids = new Set(selected.map((c) => c.id));
  delta = Math.round(delta);
  delta =
    edge === "in"
      ? Math.max(
          -Math.min(...selected.map((p) => toTimeline(p, p.sourceIn))),
          Math.min(d - 1, delta),
        )
      : Math.max(
          1 - d,
          Math.min(toTimeline(c, maxFrames - c.sourceOut), delta),
        );
  if (!delta) return doc;
  const next = clone(doc);
  const end = c.start + d;
  if (edge === "in") {
    if (ripple) {
      // Move later assembly time by the exact source delta; the selected head stays put.
      next.clips = next.clips.map((p) =>
        ids.has(p.id)
          ? {
              ...p,
              sourceIn: p.sourceIn + toSource(p, delta),
              heldRange: p.heldRange
                ? { ...p.heldRange, end: p.heldRange.end - delta }
                : p.heldRange,
            }
          : p.start >= end
            ? shifted(p, -delta)
            : p,
      );
    } else {
      let overflow = 0;
      let headShift = delta;
      if (delta < 0) {
        // Fill adjacent empty time first; any extra source extends the assembly.
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
        const available = Math.max(0, c.start - previousEnd);
        headShift = -Math.min(-delta, available);
        overflow = -delta + headShift;
      }
      next.clips = next.clips.map((p) =>
        ids.has(p.id)
          ? {
              ...p,
              sourceIn: p.sourceIn + toSource(p, delta),
              start: p.start + headShift,
            }
          : overflow && p.start >= end
            ? shifted(p, overflow)
            : p,
      );
      if (delta > 0) next.clips.push(gap(c.start, delta, c.layer));
      else consumeGaps(next, c.start + headShift, c.start, c.layer);
    }
  } else {
    next.clips = next.clips.map((p) =>
      ids.has(p.id)
        ? {
            ...p,
            sourceOut: p.sourceOut + toSource(p, delta),
            heldRange:
              ripple && p.heldRange
                ? { ...p.heldRange, end: p.heldRange.end + delta }
                : p.heldRange,
          }
        : ripple && p.start >= end
          ? shifted(p, delta)
          : p,
    );
    if (!ripple) {
      if (delta < 0) next.clips.push(gap(end + delta, -delta, c.layer));
      else {
        // Consume neighboring empty time, then ripple any extension beyond it.
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
        consumeGaps(next, end, end + bounded, c.layer);
        const overflow = delta - bounded;
        if (overflow)
          next.clips = next.clips.map((p) =>
            !ids.has(p.id) && p.start >= end + bounded
              ? shifted(p, overflow)
              : p,
          );
      }
    }
  }
  return ripple ? pack(next) : mergeGaps(next);
}
function mergeGaps(doc: Document): Document {
  const others = doc.clips.filter((c) => c.kind !== "gap" || !c.enabled);
  const gaps = doc.clips
    .filter((c) => c.kind === "gap" && c.enabled)
    .toSorted((a, b) => a.layer - b.layer || a.start - b.start);
  const merged: Clip[] = [];
  for (const c of gaps) {
    const last = merged.at(-1);
    if (
      last &&
      last.layer === c.layer &&
      last.start + duration(last) >= c.start
    ) {
      last.sourceOut =
        Math.max(last.start + duration(last), c.start + duration(c)) -
        last.start;
    } else merged.push({ ...c, sourceIn: 0, sourceOut: duration(c) });
  }
  return { ...doc, clips: [...others, ...merged] };
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
export function fitPicture(
  video: NonNullable<Asset["probe"]["video"]>,
  settings: Settings,
  fill = false,
): Transform {
  const rotated = video.rotation === 90 || video.rotation === 270;
  const w = rotated ? video.height : video.width,
    h = rotated ? video.width : video.height;
  const factor = (fill ? Math.max : Math.min)(
    settings.width / w,
    settings.height / h,
  );
  return {
    ...defaultTransform(),
    x: (settings.width - w * factor) / 2,
    y: (settings.height - h * factor) / 2,
    width: w * factor,
    height: h * factor,
  };
}

export function nextFitMode(
  clip: Clip,
  video: NonNullable<Asset["probe"]["video"]>,
  settings: Settings,
): "fit" | "fill" {
  if (clip.fitMode) return clip.fitMode === "fit" ? "fill" : "fit";
  const fitted = fitPicture(video, settings);
  return (Object.keys(fitted) as (keyof Transform)[]).every(
    (k) => Math.abs(fitted[k] - clip.transform[k]) < 0.01,
  )
    ? "fill"
    : "fit";
}

export function resize(
  doc: Document,
  old: Settings,
  width: number,
  height: number,
): Document {
  const map = (t: Transform, w: number, h: number, nw: number, nh: number) => {
    const f = Math.min(nw / w, nh / h);
    return {
      ...t,
      x: t.x * f + (nw - w * f) / 2,
      y: t.y * f + (nh - h * f) / 2,
      width: t.width * f,
      height: t.height * f,
    };
  };
  return {
    ...doc,
    clips: doc.clips.map((c) => {
      let ref = c.resizeReference;
      if (ref) {
        const expected = map(
          ref.transform,
          ref.width,
          ref.height,
          old.width,
          old.height,
        );
        if (
          (Object.keys(expected) as (keyof Transform)[]).some(
            (k) => Math.abs(expected[k] - c.transform[k]) > 0.00001,
          )
        )
          ref = undefined;
      }
      ref ??= {
        width: old.width,
        height: old.height,
        transform: clone(c.transform),
      };
      return {
        ...c,
        resizeReference: ref,
        transform: map(ref.transform, ref.width, ref.height, width, height),
      };
    }),
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
// Change the speed of a clip and its linked partner; later clips ripple by the change.
export function setSpeed(doc: Document, id: string, speed: number): Document {
  const selected = partners(doc, id),
    c = selected[0];
  speed = Math.min(10, Math.max(0.1, Math.round(speed * 1000) / 1000));
  if (!c || c.kind === "gap" || speed === speedOf(c)) return doc;
  const ids = new Set(selected.map((p) => p.id)),
    end = c.start + duration(c),
    delta = duration({ ...c, speed }) - duration(c);
  return pack({
    ...doc,
    clips: doc.clips.map((p) =>
      ids.has(p.id)
        ? { ...p, speed }
        : p.start >= end && delta
          ? shifted(p, delta)
          : p,
    ),
  });
}
