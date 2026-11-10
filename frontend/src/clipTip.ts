// Ultra short description of a clip, shown as a tooltip when hovering it in the flow
// (docs/features/editing/clip-tooltip.md). Audio clips use the analysis of their source file,
// so audio extracted from a video describes the same content as that video.
import { isStill, type Clip } from "./model";
import type { Analysis } from "./transcript";

export const TIP_LENGTH = 110;

// `text` cut at a word boundary within `max` characters, with an ellipsis.
function cutWords(text: string, max: number): string {
  const cut = text.slice(0, max - 1),
    space = cut.lastIndexOf(" ");
  return `${(space > max / 2 ? cut.slice(0, space) : cut).replace(/[\s.,;:!?-]+$/, "")}…`;
}

// The start of `text` within `max` characters: whole sentences while they fit. When they
// fill less than two thirds (a greeting, a short first sentence), the next sentence
// completes them, cut at a word boundary. The first sentence alone is cut when too long.
export function shorten(text: string, max = TIP_LENGTH): string {
  const clean = text.replace(/\s+/g, " ").trim();
  if (clean.length <= max) return clean;
  const sentences = clean.split(/(?<=[.!?…])\s+/);
  let result = "",
    used = 0;
  for (const sentence of sentences) {
    const next = result ? `${result} ${sentence}` : sentence;
    if (next.length > max) break;
    result = next;
    used++;
  }
  if (!result) return cutWords(clean, max);
  const room = max - result.length - 1;
  if (result.length < (max * 2) / 3 && used < sentences.length && room >= 20)
    return `${result} ${cutWords(sentences[used], room)}`;
  return result;
}

// The tooltip of a clip, or undefined when it has none (empty clips). `analysis` is the
// analysis of the clip's source: undefined while loading, null when there is none.
export function clipTip(
  clip: Clip,
  analysis: Analysis | null | undefined,
): string | undefined {
  if (clip.kind === "gap") return undefined;
  if (clip.kind === "text")
    return clip.title ? shorten(clip.title.text) : clip.name;
  if (analysis && !isStill(clip)) {
    if (analysis.summary.trim()) return shorten(analysis.summary);
    if (analysis.keywords.length)
      return shorten(analysis.keywords.slice(0, 5).join(", "));
  }
  return clip.name;
}
