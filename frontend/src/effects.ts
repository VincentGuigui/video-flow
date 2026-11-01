// Clip effects shown as cards in the Effects tab of the properties panel. Each entry
// says which clips it applies to, whether it is in use, a one-line summary, and how to
// add (default values) or remove it. New effects are added to EFFECTS; the interface
// lists them in "Add effect" without further changes.
import { partners, setSpeed, speedOf, type Clip, type Document } from "./model";
import { setFade } from "./transitions";
import { withVolumeRanges } from "./volume";

export type EffectId =
  "fadeIn" | "fadeOut" | "speed" | "zoom" | "mute" | "duck";

export interface EffectDef {
  id: EffectId;
  label: string;
  description: string;
  applies: (doc: Document, clip: Clip) => boolean;
  active: (doc: Document, clip: Clip) => boolean;
  summary: (doc: Document, clip: Clip, rate: number) => string;
  // A new document, or null when adding only opens the card (values chosen in it).
  add: (doc: Document, clip: Clip, rate: number) => Document | null;
  remove: (doc: Document, clip: Clip) => Document;
}

const audioOf = (doc: Document, clip: Clip) =>
  partners(doc, clip.id).find((c) => c.kind === "audio");
const ranges = (doc: Document, clip: Clip, kind: "mute" | "duck") =>
  (audioOf(doc, clip)?.volumeRanges ?? []).filter((r) => r.kind === kind);
const withoutRanges = (doc: Document, clip: Clip, kind: "mute" | "duck") => {
  const audio = audioOf(doc, clip);
  return audio
    ? withVolumeRanges(doc, new Set([audio.id]), (c) =>
        (c.volumeRanges ?? []).filter((r) => r.kind !== kind),
      )
    : doc;
};
const seconds = (frames: number, rate: number) =>
  `${(frames / rate).toFixed(2)} s`;
const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? "" : "s"}`;

function fade(
  edge: "fadeIn" | "fadeOut",
  label: string,
  description: string,
): EffectDef {
  return {
    id: edge,
    label,
    description,
    applies: (_, clip) => clip.kind !== "gap",
    active: (_, clip) => (clip[edge] ?? 0) > 0,
    summary: (_, clip, rate) => seconds(clip[edge] ?? 0, rate),
    add: (doc, clip, rate) =>
      setFade(doc, clip.id, edge, Math.round(0.5 * rate)),
    remove: (doc, clip) => setFade(doc, clip.id, edge, 0),
  };
}

export const EFFECTS: EffectDef[] = [
  fade("fadeIn", "Fade in", "From black (or what lies below) at the start"),
  fade("fadeOut", "Fade out", "To black (or what lies below) at the end"),
  {
    id: "speed",
    label: "Speed",
    description: "Play faster or slower; sound keeps its pitch",
    applies: (_, clip) => clip.kind === "video" || clip.kind === "audio",
    active: (_, clip) => Math.abs(speedOf(clip) - 1) > 0.001,
    summary: (_, clip) => `${Math.round(speedOf(clip) * 100)} %`,
    add: () => null,
    remove: (doc, clip) => setSpeed(doc, clip.id, 1),
  },
  {
    id: "zoom",
    label: "Zoom & pan",
    description: "Push in toward a point over a range",
    applies: (_, clip) => clip.kind === "video",
    active: (_, clip) => (clip.zooms ?? []).length > 0,
    summary: (_, clip) => plural((clip.zooms ?? []).length, "zoom"),
    add: () => null,
    remove: (doc, clip) => ({
      ...doc,
      clips: doc.clips.map((c) => (c.id === clip.id ? { ...c, zooms: [] } : c)),
    }),
  },
  {
    id: "mute",
    label: "Mute ranges",
    description: "Silence parts of the sound; the picture is kept",
    applies: (doc, clip) => clip.kind !== "gap" && !!audioOf(doc, clip),
    active: (doc, clip) => ranges(doc, clip, "mute").length > 0,
    summary: (doc, clip) => plural(ranges(doc, clip, "mute").length, "range"),
    add: () => null,
    remove: (doc, clip) => withoutRanges(doc, clip, "mute"),
  },
  {
    id: "duck",
    label: "Ducking",
    description: "Lower music by 15 dB under transcribed speech",
    applies: (_, clip) => clip.kind === "audio" && !clip.linkId,
    active: (doc, clip) => ranges(doc, clip, "duck").length > 0,
    summary: (doc, clip) => plural(ranges(doc, clip, "duck").length, "range"),
    add: () => null,
    remove: (doc, clip) => withoutRanges(doc, clip, "duck"),
  },
];
