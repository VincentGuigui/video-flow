import { describe, expect, it } from "vitest";
import {
  clampWidth,
  DEFAULT_PANEL,
  PANEL_MAX,
  PANEL_MIN,
  parseLayout,
} from "./panel";

describe("properties panel layout", () => {
  it("clamps the width to its bounds and half the available space", () => {
    expect(clampWidth(50)).toBe(PANEL_MIN);
    expect(clampWidth(5000)).toBe(PANEL_MAX);
    expect(clampWidth(500, 800)).toBe(400);
    expect(clampWidth(500, 300)).toBe(PANEL_MIN);
    expect(clampWidth(300.4)).toBe(300);
  });

  it("reads a stored layout and falls back on defaults", () => {
    expect(parseLayout(null)).toEqual(DEFAULT_PANEL);
    expect(parseLayout("not json")).toEqual(DEFAULT_PANEL);
    expect(
      parseLayout(
        JSON.stringify({ width: 320, height: "tall", pinned: false }),
      ),
    ).toEqual({ width: 320, height: "tall", pinned: false });
    expect(parseLayout(JSON.stringify({ width: 9999, height: "x" }))).toEqual({
      width: PANEL_MAX,
      height: "half",
      pinned: true,
    });
  });
});
