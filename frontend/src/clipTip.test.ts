import { describe, expect, it } from "vitest";
import { defaultTransform, type Clip } from "./model";
import { clipTip, shorten, TIP_LENGTH } from "./clipTip";
import type { Analysis } from "./transcript";

const clip = (kind: Clip["kind"], extra: Partial<Clip> = {}): Clip => ({
  id: "c",
  kind,
  linkId: null,
  assetId: "a",
  name: "take-01.mp4",
  start: 0,
  sourceIn: 0,
  sourceOut: 50,
  layer: 0,
  enabled: true,
  gainDb: 0,
  transform: defaultTransform(),
  ...extra,
});
const analysis = (summary: string, keywords: string[] = []): Analysis => ({
  summary,
  keywords,
});

describe("clip tooltip", () => {
  it("keeps whole sentences within the limit and cuts a long first one at a word", () => {
    expect(shorten("Bonjour. Aujourd'hui on parle de montage.")).toBe(
      "Bonjour. Aujourd'hui on parle de montage.",
    );
    const text =
      "Une première phrase courte. Une deuxième phrase qui est beaucoup plus longue que la limite des cent dix caractères autorisés.";
    // A short first sentence is completed with the start of the next one.
    const completed = shorten(text);
    expect(
      completed.startsWith("Une première phrase courte. Une deuxième phrase"),
    ).toBe(true);
    expect(completed.length).toBeLessThanOrEqual(TIP_LENGTH);
    expect(completed.endsWith("…")).toBe(true);
    // Sentences that fill the limit are kept whole, the rest is dropped.
    const full =
      "Voici une première phrase assez longue pour remplir presque toute la ligne. Et une autre.";
    expect(shorten(full, 80)).toBe(
      "Voici une première phrase assez longue pour remplir presque toute la ligne.",
    );
    const long = "mot ".repeat(60);
    const cut = shorten(long);
    expect(cut.length).toBeLessThanOrEqual(TIP_LENGTH);
    expect(cut.endsWith("mot…")).toBe(true);
  });

  it("describes video and audio clips from the analysis of their source", () => {
    const a = analysis("On présente le projet. Puis le planning.", ["projet"]);
    const video = clipTip(clip("video"), a);
    // Audio extracted from the same file gets the very same description.
    expect(clipTip(clip("audio"), a)).toBe(video);
    expect(video).toBe("On présente le projet. Puis le planning.");
  });

  it("falls back on keywords, then on the clip name", () => {
    expect(clipTip(clip("audio"), analysis("", ["budget", "planning"]))).toBe(
      "budget, planning",
    );
    expect(clipTip(clip("audio"), analysis(""))).toBe("take-01.mp4");
    expect(clipTip(clip("video"), null)).toBe("take-01.mp4");
    expect(clipTip(clip("video"), undefined)).toBe("take-01.mp4");
  });

  it("names images, freeze frames and text clips, and skips empty clips", () => {
    const a = analysis("Un résumé.");
    expect(clipTip(clip("video", { stillFrame: 0, name: "card.png" }), a)).toBe(
      "card.png",
    );
    const title = {
      text: "Chapitre 1\nIntroduction",
      style: "title" as const,
      size: 0.08,
      color: "#fff",
      box: false,
      boxColor: "#000",
      boxOpacity: 0.7,
    };
    expect(clipTip(clip("text", { assetId: null, title }), null)).toBe(
      "Chapitre 1 Introduction",
    );
    expect(clipTip(clip("gap", { assetId: null }), null)).toBeUndefined();
  });
});
