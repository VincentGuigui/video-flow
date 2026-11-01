// Keyframed transforms (docs/features/keyframes.md). Mirror of
// backend/videoflow/editor/keyframes.py: keep both in step.
import {
  clone,
  duration,
  speedOf,
  type Clip,
  type Document,
  type Transform,
} from "./model";

export interface Keyframe {
  frame: number; // source frame
  transform: Transform;
  ease?: "linear" | "smooth"; // shape of the change starting here (default smooth)
}

// Transform values interpolated between keyframes.
export const ANIMATED = [
  "x",
  "y",
  "width",
  "height",
  "cropLeft",
  "cropRight",
  "cropTop",
  "cropBottom",
  "rotation",
  "opacity",
] as const;
type Animated = (typeof ANIMATED)[number];

export const smooth = (u: number) => {
  u = Math.min(1, Math.max(0, u));
  return u * u * (3 - 2 * u);
};

const valueOf = (t: Transform, name: Animated) =>
  t[name] ?? (name === "opacity" ? 1 : 0);

// The transform at a source frame: keyframes interpolated, held before the first and
// after the last; the clip's transform without keyframes.
export function transformAt(clip: Clip, sourceFrame: number): Transform {
  const keys = clip.keyframes ?? [];
  if (!keys.length) return clip.transform;
  if (sourceFrame <= keys[0].frame) return keys[0].transform;
  const last = keys[keys.length - 1];
  if (sourceFrame >= last.frame) return last.transform;
  const index = keys.findLastIndex((k) => k.frame <= sourceFrame),
    a = keys[index],
    b = keys[index + 1];
  let u = (sourceFrame - a.frame) / (b.frame - a.frame);
  if ((a.ease ?? "smooth") === "smooth") u = smooth(u);
  const result = { ...a.transform };
  for (const name of ANIMATED) {
    const start = valueOf(a.transform, name);
    result[name] = start + (valueOf(b.transform, name) - start) * u;
  }
  return result;
}

// Source frame shown at a timeline frame of the (laid-out) clip.
export const sourceAt = (clip: Clip, frame: number) =>
  clip.sourceIn + Math.round((frame - clip.start) * speedOf(clip));
// Timeline frame of a source frame of the clip.
export const timelineAt = (clip: Clip, source: number) =>
  clip.start + Math.round((source - clip.sourceIn) / speedOf(clip));

export const transformAtFrame = (clip: Clip, frame: number) =>
  transformAt(clip, sourceAt(clip, frame));

// Keyframes shown on the timeline: inside the clip's visible source range.
export const visibleKeyframes = (clip: Clip) =>
  (clip.keyframes ?? []).filter(
    (k) => k.frame >= clip.sourceIn && k.frame < clip.sourceOut,
  );

function withKeyframes(doc: Document, id: string, keyframes: Keyframe[]) {
  return {
    ...doc,
    clips: doc.clips.map((c) =>
      c.id === id
        ? { ...c, keyframes: keyframes.toSorted((a, b) => a.frame - b.frame) }
        : c,
    ),
  };
}

// Set the transform shown at a timeline frame. With keyframes, the keyframe there is
// created or replaced (auto-key); without, the clip's transform changes.
export function setTransformAt(
  doc: Document,
  id: string,
  frame: number,
  transform: Transform,
  placed: Clip,
): Document {
  const clip = doc.clips.find((c) => c.id === id);
  if (!clip) return doc;
  if (!clip.keyframes?.length)
    return {
      ...doc,
      clips: doc.clips.map((c) => (c.id === id ? { ...c, transform } : c)),
    };
  const source = sourceAt(placed, frame),
    existing = clip.keyframes.find((k) => k.frame === source);
  return withKeyframes(doc, id, [
    ...clip.keyframes.filter((k) => k.frame !== source),
    { ease: existing?.ease ?? "smooth", frame: source, transform },
  ]);
}

// Add a keyframe at a timeline frame holding the transform shown there. The first
// keyframe of a clip also sets its transform, so the clip looks the same.
export function addKeyframe(
  doc: Document,
  id: string,
  frame: number,
  placed: Clip,
): Document {
  const clip = doc.clips.find((c) => c.id === id);
  if (!clip || clip.kind !== "video") return doc;
  const source = sourceAt(placed, frame);
  if (clip.keyframes?.some((k) => k.frame === source)) return doc;
  return withKeyframes(doc, id, [
    ...(clip.keyframes ?? []),
    {
      frame: source,
      transform: clone(transformAt(clip, source)),
      ease: "smooth",
    },
  ]);
}

// Remove one keyframe; the last one leaves its transform as the clip's transform.
export function removeKeyframe(
  doc: Document,
  id: string,
  source: number,
): Document {
  const clip = doc.clips.find((c) => c.id === id);
  const key = clip?.keyframes?.find((k) => k.frame === source);
  if (!clip || !key) return doc;
  const rest = clip.keyframes!.filter((k) => k !== key);
  if (rest.length) return withKeyframes(doc, id, rest);
  return {
    ...doc,
    clips: doc.clips.map((c) =>
      c.id === id ? { ...c, keyframes: [], transform: key.transform } : c,
    ),
  };
}

// Move a keyframe to another source frame inside the clip's visible range, never onto
// another keyframe.
export function moveKeyframe(
  doc: Document,
  id: string,
  from: number,
  to: number,
): Document {
  const clip = doc.clips.find((c) => c.id === id);
  const key = clip?.keyframes?.find((k) => k.frame === from);
  if (!clip || !key) return doc;
  const target = Math.min(
    clip.sourceOut - 1,
    Math.max(clip.sourceIn, Math.round(to)),
  );
  if (clip.keyframes!.some((k) => k !== key && k.frame === target)) return doc;
  return withKeyframes(doc, id, [
    ...clip.keyframes!.filter((k) => k !== key),
    { ...key, frame: target },
  ]);
}

export function setEase(
  doc: Document,
  id: string,
  source: number,
  ease: "linear" | "smooth",
): Document {
  const clip = doc.clips.find((c) => c.id === id);
  if (!clip?.keyframes?.some((k) => k.frame === source)) return doc;
  return withKeyframes(
    doc,
    id,
    clip.keyframes.map((k) => (k.frame === source ? { ...k, ease } : k)),
  );
}

// Remove every keyframe; the clip keeps the transform shown at `frame`.
export function clearKeyframes(
  doc: Document,
  id: string,
  frame: number,
  placed: Clip,
): Document {
  const clip = doc.clips.find((c) => c.id === id);
  if (!clip?.keyframes?.length) return doc;
  const transform = clone(transformAtFrame(placed, frame));
  return {
    ...doc,
    clips: doc.clips.map((c) =>
      c.id === id ? { ...c, keyframes: [], transform } : c,
    ),
  };
}

// Frames from the clip start to each visible keyframe, for timelines and the flow.
export const keyframeOffsets = (clip: Clip) =>
  visibleKeyframes(clip).map((k) => ({
    frame: k.frame,
    offset: Math.min(
      duration(clip) - 1,
      Math.round((k.frame - clip.sourceIn) / speedOf(clip)),
    ),
  }));
