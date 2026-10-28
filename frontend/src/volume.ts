// Mirror of backend/videoflow/editor/volume.py: keep both in step.
import {
  duration,
  layout,
  speedOf,
  toTimeline,
  type Clip,
  type Document,
} from "./model";
import type { Word } from "./transcript";

export interface VolumeRange {
  start: number; // source frames
  end: number;
  gainDb: number; // -60 = silence
  ramp: number; // source frames, outside the range
  kind: "mute" | "duck";
}

const factor = (r: VolumeRange) =>
  r.gainDb <= -60 ? 0 : 10 ** (r.gainDb / 20);

export function rangeFactor(r: VolumeRange, sourceFrame: number): number {
  const u = r.ramp
    ? Math.min(
        (sourceFrame - (r.start - r.ramp)) / r.ramp,
        (r.end + r.ramp - sourceFrame) / r.ramp,
      )
    : sourceFrame >= r.start && sourceFrame < r.end
      ? 1
      : 0;
  return 1 - (1 - factor(r)) * Math.min(1, Math.max(0, u));
}

// Gain factor of a clip's volume ranges at a timeline frame.
export function envelopeAt(clip: Clip, frame: number): number {
  const source = clip.sourceIn + (frame - clip.start) * speedOf(clip);
  return Math.min(
    1,
    ...(clip.volumeRanges ?? []).map((r) => rangeFactor(r, source)),
  );
}

// The source range of `clip` under a timeline range, or null when they do not overlap.
export function sourceRange(
  doc: Document,
  clip: Clip,
  range: { start: number; end: number },
): { start: number; end: number } | null {
  const placed = layout(doc).clips.find((c) => c.id === clip.id);
  if (!placed) return null;
  const a = Math.max(range.start, placed.start),
    b = Math.min(range.end, placed.start + duration(placed));
  if (b <= a) return null;
  const at = (frame: number) =>
    clip.sourceIn + Math.round((frame - placed.start) * speedOf(clip));
  return { start: at(a), end: at(b) };
}

// Duck `musicId` under the speech of every other enabled clip with a transcript:
// speech is merged across gaps under 0.5 s, padded by 0.2 s before and 0.3 s after.
export function duckRanges(
  doc: Document,
  musicId: string,
  words: Record<string, Word[]>,
  rate: number,
  gainDb = -15,
): VolumeRange[] {
  const placed = layout(doc).clips,
    music = placed.find((c) => c.id === musicId);
  if (!music) return [];
  const speech: [number, number][] = [];
  for (const c of placed) {
    if (c.id === musicId || c.kind !== "audio" || !c.assetId) continue;
    const inUs = (c.sourceIn * 1e6) / rate,
      outUs = (c.sourceOut * 1e6) / rate;
    for (const w of words[c.assetId] ?? []) {
      if (w.endUs <= inUs || w.startUs >= outUs) continue;
      const frame = (us: number) =>
        c.start + toTimeline(c, Math.round((us * rate) / 1e6) - c.sourceIn);
      speech.push([
        frame(Math.max(w.startUs, inUs)),
        frame(Math.min(w.endUs, outUs)),
      ]);
    }
  }
  speech.sort((a, b) => a[0] - b[0]);
  const merged: [number, number][] = [],
    gap = Math.round(rate * 0.5);
  for (const [a, b] of speech) {
    const last = merged.at(-1);
    if (last && a - last[1] < gap) last[1] = Math.max(last[1], b);
    else merged.push([a, b]);
  }
  const ramp = Math.max(1, Math.round(rate * 0.3 * speedOf(music)));
  return merged
    .map(([a, b]) =>
      sourceRange(doc, music, {
        start: a - Math.round(rate * 0.2),
        end: b + Math.round(rate * 0.3),
      }),
    )
    .filter((r) => r !== null)
    .map((r) => ({ ...r, gainDb, ramp, kind: "duck" as const }));
}

// Apply ranges to the audio clips among a clip and its linked partner.
export function withVolumeRanges(
  doc: Document,
  ids: Set<string>,
  update: (clip: Clip) => VolumeRange[],
): Document {
  return {
    ...doc,
    clips: doc.clips.map((c) =>
      ids.has(c.id) && c.kind === "audio"
        ? { ...c, volumeRanges: update(c) }
        : c,
    ),
  };
}
