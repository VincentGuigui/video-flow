import {
  duration,
  layout,
  pack,
  remove,
  split,
  trim,
  type Document,
} from "./model";

export interface Range {
  start: number;
  end: number;
}
export type Handle = "start" | "end";

const CONTEXT_SECONDS = 2;

// The focused clip plus two seconds on either side, else the whole assembly.
export function defaultRange(
  doc: Document,
  focus: string | null,
  rate: number,
): Range {
  const r = layout(doc),
    clip = r.clips.find((c) => c.id === focus),
    context = Math.round(rate * CONTEXT_SECONDS);
  return clip
    ? {
        start: Math.max(0, clip.start - context),
        end: Math.min(r.total, clip.start + duration(clip) + context),
      }
    : { start: 0, end: r.total };
}

export function clampRange(range: Range, total: number): Range {
  const start = Math.max(0, Math.min(total, Math.round(range.start)));
  return {
    start,
    end: Math.max(start, Math.min(total, Math.round(range.end))),
  };
}

// What Space plays: the range, or two seconds around the selected handle.
export function playWindow(
  range: Range,
  handle: Handle | null,
  rate: number,
  total: number,
): Range {
  if (!handle) return clampRange(range, total);
  const at = range[handle],
    context = Math.round(rate * CONTEXT_SECONDS);
  return clampRange({ start: at - context, end: at + context }, total);
}

// Play from the cursor when it is inside the window, otherwise from its start.
export function playStart(window: Range, frame: number): number {
  return frame >= window.start && frame < window.end - 1 ? frame : window.start;
}

// Move one handle, keeping at least one frame between start and end.
export function moveHandle(
  range: Range,
  handle: Handle,
  frame: number,
  total: number,
): Range {
  const f = Math.max(0, Math.min(total, Math.round(frame)));
  return handle === "start"
    ? { start: Math.min(f, range.end - 1), end: range.end }
    : { start: range.start, end: Math.max(f, range.start + 1) };
}

// Shrink a clip (and its linked partner) to the part inside `range`, rippling
// later clips earlier. Returns null when the range does not shorten the clip.
export function trimToRange(
  doc: Document,
  id: string,
  range: Range,
): Document | null {
  let next = pack(doc);
  const clip = layout(next).clips.find((c) => c.id === id);
  if (!clip) return null;
  const end = clip.start + duration(clip),
    head = Math.max(0, range.start - clip.start),
    tail = Math.max(0, end - range.end);
  if (range.end <= clip.start || range.start >= end) return null;
  if (!head && !tail) return null;
  if (head + tail >= duration(clip)) return null;
  if (head) next = trim(next, id, "in", head, true, Infinity);
  if (tail) next = trim(next, id, "out", -tail, true, Infinity);
  return next;
}

// Cut the part of a clip (and its linked partner) inside `range` out of the edit,
// rippling later clips earlier. Null when the range does not cut into the clip's
// middle; a range touching an edge is a trim (see trimToRange).
export function deleteRange(
  doc: Document,
  id: string,
  range: Range,
): Document | null {
  let next = pack(doc);
  const clip = layout(next).clips.find((c) => c.id === id);
  if (!clip) return null;
  const start = Math.max(range.start, clip.start),
    end = Math.min(range.end, clip.start + duration(clip));
  if (end <= start) return null;
  if (start === clip.start && end === clip.start + duration(clip)) return null;
  if (start === clip.start || end === clip.start + duration(clip))
    return trimToRange(next, id, {
      start: start === clip.start ? end : clip.start,
      end: start === clip.start ? clip.start + duration(clip) : start,
    });
  next = split(next, id, start);
  const middle = next.clips.find(
    (c) => c.start === start && c.kind === clip.kind && c.layer === clip.layer,
  );
  if (!middle) return null;
  next = split(next, middle.id, end);
  return remove(next, middle.id, true);
}

export interface TimedWord {
  startUs: number;
  endUs: number;
}

// Trim leading and trailing silence to the first and last spoken word inside the
// clip, keeping some padding. Null when there is no speech or nothing to remove.
export function autoTrim(
  doc: Document,
  id: string,
  words: TimedWord[],
  rate: number,
  padding = { beforeUs: 150_000, afterUs: 300_000 },
): Document | null {
  const clip = doc.clips.find((c) => c.id === id);
  if (!clip || clip.kind === "gap") return null;
  const toUs = (f: number) => (f * 1_000_000) / rate,
    inUs = toUs(clip.sourceIn),
    outUs = toUs(clip.sourceOut);
  const spoken = words.filter((w) => w.endUs > inUs && w.startUs < outUs);
  if (!spoken.length) return null;
  const first = Math.max(
      clip.sourceIn,
      Math.floor(((spoken[0].startUs - padding.beforeUs) * rate) / 1_000_000),
    ),
    last = Math.min(
      clip.sourceOut,
      Math.ceil(((spoken.at(-1)!.endUs + padding.afterUs) * rate) / 1_000_000),
    );
  const placed = layout(pack(doc)).clips.find((c) => c.id === id);
  if (!placed || last <= first) return null;
  return trimToRange(doc, id, {
    start: placed.start + first - clip.sourceIn,
    end: placed.start + last - clip.sourceIn,
  });
}
