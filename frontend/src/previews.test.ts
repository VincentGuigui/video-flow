import { describe, expect, it } from "vitest";
import { mediaUrl, playable, stillUrl, type PreviewState } from "./previews";

const state = (values: Partial<PreviewState>): PreviewState => ({
  video: false,
  audio: false,
  stills: 0,
  state: "pending",
  progress: null,
  error: null,
  ...values,
});

describe("preview media", () => {
  it("plays the video once ready, the sound before", () => {
    const quick = state({ audio: true, stills: 5, state: "stills" });
    expect(playable(quick, true)).toBe(true);
    expect(playable(quick, false)).toBe(false);
    expect(mediaUrl("a", quick)).toBe("/api/media/a?part=audio");
    const ready = state({ video: true, state: "ready" });
    expect(playable(ready, false)).toBe(true);
    expect(mediaUrl("a", ready)).toBe("/api/media/a");
    // Audio files the editor plays as they are: ready without any preview.
    expect(playable(state({ state: "ready" }), true)).toBe(true);
    expect(playable(undefined, true)).toBe(false);
  });

  it("asks for the still of the current second", () => {
    expect(stillUrl("a", 2.9)).toBe("/api/previews/a/still/2");
    expect(stillUrl("a", -1)).toBe("/api/previews/a/still/0");
  });
});
