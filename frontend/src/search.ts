// Search of what is said in the clips of the edit (docs/features/editing/text-search.md).
import { create } from "zustand";
import { isStill, layout, toTimeline, type Document } from "./model";
import { sourceFrame, type Analysis, type Word } from "./transcript";

// Lower case, without accents or punctuation, so "Été," matches "ete".
export const normalize = (text: string) =>
  text
    .normalize("NFD")
    .replace(/\p{M}/gu, "")
    .toLowerCase()
    .replace(/[^\p{L}\p{N}]+/gu, " ")
    .trim();

export const terms = (query: string) =>
  normalize(query).split(" ").filter(Boolean);

// Word ranges matching the query: consecutive words, each equal to its term, except the
// last term which may start a word (typing "intro" finds "introduction").
export function findWords(
  query: string,
  words: Word[],
): { startUs: number; endUs: number }[] {
  const wanted = terms(query);
  if (!wanted.length) return [];
  const said = words.map((w) => normalize(w.text).replace(/ /g, ""));
  const found: { startUs: number; endUs: number }[] = [];
  for (let i = 0; i + wanted.length <= said.length; i++) {
    const hit = wanted.every((term, j) =>
      j === wanted.length - 1
        ? said[i + j].startsWith(term)
        : said[i + j] === term,
    );
    if (hit)
      found.push({
        startUs: words[i].startUs,
        endUs: words[i + wanted.length - 1].endUs,
      });
  }
  return found;
}

export interface Hit {
  clipId: string;
  // Assembly frame of the first word, and its offset from the clip start.
  frame: number;
  offset: number;
}

// Occurrences in the clips of the assembly, in timeline order. A source is searched once
// per clip: through its video clip when its audio is linked to it.
export function searchHits(
  doc: Document,
  analyses: Record<string, Analysis | null | undefined>,
  query: string,
  rate: number,
): Hit[] {
  if (!terms(query).length) return [];
  const placed = new Map(layout(doc).clips.map((c) => [c.id, c]));
  const hits: Hit[] = [];
  for (const clip of doc.clips) {
    const at = placed.get(clip.id);
    const words = analyses[clip.assetId ?? ""]?.words;
    if (!at || !words?.length) continue;
    if ((clip.kind !== "video" && clip.kind !== "audio") || isStill(clip))
      continue;
    if (
      clip.kind === "audio" &&
      clip.linkId &&
      doc.clips.some(
        (c) =>
          c.kind === "video" &&
          c.linkId === clip.linkId &&
          c.assetId === clip.assetId &&
          placed.has(c.id),
      )
    )
      continue;
    for (const { startUs } of findWords(query, words)) {
      const source = sourceFrame(startUs, rate);
      if (source < clip.sourceIn || source >= clip.sourceOut) continue;
      const offset = toTimeline(clip, source - clip.sourceIn);
      hits.push({ clipId: clip.id, frame: at.start + offset, offset });
    }
  }
  return hits.sort((a, b) => a.frame - b.frame);
}

// The occurrence after (or before) the cursor, wrapping around the edit.
export function nextHit(hits: Hit[], frame: number, back = false): Hit | null {
  if (!hits.length) return null;
  return back
    ? (hits.findLast((h) => h.frame < frame) ?? hits.at(-1)!)
    : (hits.find((h) => h.frame > frame) ?? hits[0]);
}

// Clips to highlight, with the offsets of their occurrences: a linked video and its
// audio share the marks.
export function hitMarks(doc: Document, hits: Hit[]) {
  const marks = new Map<string, number[]>();
  for (const hit of hits) {
    const clip = doc.clips.find((c) => c.id === hit.clipId);
    const ids = clip?.linkId
      ? doc.clips
          .filter((c) => c.linkId === clip.linkId && c.assetId === clip.assetId)
          .map((c) => c.id)
      : [hit.clipId];
    for (const id of ids) marks.set(id, [...(marks.get(id) ?? []), hit.offset]);
  }
  return marks;
}

interface Search {
  query: string;
  hits: Hit[];
  set: (values: Partial<Omit<Search, "set">>) => void;
}
export const useSearch = create<Search>((set) => ({
  query: "",
  hits: [],
  set,
}));
