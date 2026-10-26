import { layout, type Document } from "./model";

export interface Sentence {
  startUs: number;
  endUs: number;
  text: string;
}
export interface Topic {
  startUs: number;
  endUs: number;
  title: string;
  sentences: Sentence[];
}
export interface Analysis {
  summary: string;
  keywords: string[];
  topics?: Topic[];
}

export const sourceFrame = (us: number, rate: number) =>
  Math.round((us * rate) / 1_000_000);

// Assembly frame of a source time inside the clip's trimmed range, or null when the
// time is outside it or the clip is not in the assembly (disabled).
export function assemblyFrame(
  doc: Document,
  clipId: string,
  us: number,
  rate: number,
): number | null {
  const clip = doc.clips.find((c) => c.id === clipId);
  const placed = layout(doc).clips.find((c) => c.id === clipId);
  if (!clip || !placed) return null;
  const frame = sourceFrame(us, rate);
  if (frame < clip.sourceIn || frame >= clip.sourceOut) return null;
  return placed.start + frame - clip.sourceIn;
}

// Assembly range covered by a source range, clamped to the clip's trimmed range.
export function assemblyRange(
  doc: Document,
  clipId: string,
  startUs: number,
  endUs: number,
  rate: number,
): { start: number; end: number } | null {
  const clip = doc.clips.find((c) => c.id === clipId);
  const placed = layout(doc).clips.find((c) => c.id === clipId);
  if (!clip || !placed) return null;
  const a = Math.max(clip.sourceIn, sourceFrame(startUs, rate)),
    b = Math.min(clip.sourceOut, sourceFrame(endUs, rate));
  if (b <= a) return null;
  return {
    start: placed.start + a - clip.sourceIn,
    end: placed.start + b - clip.sourceIn,
  };
}
