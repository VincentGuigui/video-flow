import { duration, pack, partners, type Clip, type Document } from "./model";
import type { Word } from "./transcript";

// Video takes stacked over the same assembly time as the selected clip, enabled or
// not, ordered by lane. A selected audio clip stands for its linked video.
export function stackedTakes(doc: Document, id: string): Clip[] {
  const packed = pack(doc);
  let clip = packed.clips.find((c) => c.id === id);
  if (clip?.kind === "audio")
    clip = partners(packed, id).find((c) => c.kind === "video");
  if (!clip || clip.kind !== "video") return [];
  const start = clip.start,
    end = clip.start + duration(clip);
  return packed.clips
    .filter(
      (c) =>
        c.kind === "video" &&
        c.start < end &&
        c.start + duration(c) > start &&
        (c.id === clip.id || c.layer !== clip.layer),
    )
    .toSorted((a, b) => a.layer - b.layer || a.start - b.start);
}

// Enable the picked take and its linked audio; disable the other takes and theirs.
export function pickTake(doc: Document, takes: Clip[], id: string): Document {
  const on = new Set(partners(doc, id).map((c) => c.id));
  const off = new Set(
    takes
      .filter((t) => t.id !== id)
      .flatMap((t) => partners(doc, t.id).map((c) => c.id)),
  );
  return pack({
    ...doc,
    clips: doc.clips.map((c) =>
      on.has(c.id)
        ? { ...c, enabled: true }
        : off.has(c.id)
          ? { ...c, enabled: false }
          : c,
    ),
  });
}

export const normalize = (text: string) =>
  text
    .normalize("NFKD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/[^\p{L}\p{N}]+/gu, "");

// Words spoken inside a take's trimmed source range.
export function takeWords(clip: Clip, words: Word[], rate: number): Word[] {
  const inUs = (clip.sourceIn * 1_000_000) / rate,
    outUs = (clip.sourceOut * 1_000_000) / rate;
  return words.filter((w) => w.startUs >= inUs && w.endUs <= outUs);
}

// The first word of the reference take that every other take also says, and the
// source time of its first occurrence in each take (null when there is none).
// Longer words come first: short ones ("the", "la") recur and misalign takes.
export function anchor(
  takes: Word[][],
  reference = 0,
): { word: string; times: number[] } | null {
  const sets = takes.map((ws) => new Set(ws.map((w) => normalize(w.text))));
  for (const minimum of [4, 2])
    for (const w of takes[reference] ?? []) {
      const key = normalize(w.text);
      if (key.length < minimum || !sets.every((s) => s.has(key))) continue;
      return {
        word: w.text,
        times: takes.map(
          (ws) => ws.find((x) => normalize(x.text) === key)!.startUs,
        ),
      };
    }
  return null;
}

// Per take, which words no other take says.
export function divergent(takes: Word[][]): boolean[][] {
  const sets = takes.map((ws) => new Set(ws.map((w) => normalize(w.text))));
  return takes.map((ws, i) =>
    ws.map((w) => {
      const key = normalize(w.text);
      return !!key && sets.every((s, j) => j === i || !s.has(key));
    }),
  );
}
