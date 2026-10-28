// Mirror of backend/videoflow/editor/zoom.py: keep both in step.
import type { Clip } from "./model";

export interface Zoom {
  start: number; // source frames
  end: number;
  scale: number;
  x: number; // focus point in the picture, 0..1 from the left
  y: number; // 0..1 from the top
  easeIn: number; // source frames
  easeOut: number;
}

const ease = (u: number) => {
  u = Math.min(1, Math.max(0, u));
  return u * u * (3 - 2 * u);
};

export function ramps(z: Zoom): [number, number] {
  const length = z.end - z.start,
    easeIn = Math.min(z.easeIn, length);
  return [easeIn, Math.min(z.easeOut, length - easeIn)];
}

export function amount(z: Zoom, sourceFrame: number): number {
  const [easeIn, easeOut] = ramps(z),
    f = sourceFrame;
  if (f < z.start || f >= z.end) return 0;
  if (easeIn && f < z.start + easeIn) return ease((f - z.start) / easeIn);
  if (easeOut && f >= z.end - easeOut) return ease((z.end - f) / easeOut);
  return 1;
}

// Zoom factor and focus of a clip at a timeline frame.
export function zoomAt(
  clip: Clip,
  frame: number,
): { factor: number; x: number; y: number } {
  const source = clip.sourceIn + (frame - clip.start) * (clip.speed ?? 1);
  let factor = 1,
    x = 0.5,
    y = 0.5;
  for (const z of clip.zooms ?? []) {
    const a = amount(z, source);
    factor += (z.scale - 1) * a;
    if (source >= z.start && source <= z.end) [x, y] = [z.x, z.y];
  }
  return { factor, x, y };
}

// A zoom over the part of a clip inside a timeline range, with the default easing
// (in 0.3 s, out 1 s, from the user's Camtasia habits; spec 21).
export function zoomForRange(
  clip: Clip,
  range: { start: number; end: number },
  rate: number,
  scale = 2,
  focus = { x: 0.5, y: 0.5 },
): Zoom | null {
  const speed = clip.speed ?? 1,
    toSource = (frame: number) =>
      clip.sourceIn + Math.round((frame - clip.start) * speed),
    start = Math.max(clip.sourceIn, toSource(range.start)),
    end = Math.min(clip.sourceOut, toSource(range.end));
  if (end - start < 2) return null;
  return {
    start,
    end,
    scale,
    ...focus,
    easeIn: Math.round(0.3 * rate * speed),
    easeOut: Math.round(1 * rate * speed),
  };
}
