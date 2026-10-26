import { expect, it } from "vitest";
import { useTimeline, zoomTimeline, TIMELINE_ORIGIN } from "./timeline";

it("zooms a single shared time axis around the pointer", () => {
  useTimeline.setState({ scale: 2, scroll: 120, width: 1000, fitting: true });
  const pointer = 400;
  const frame = (120 + pointer - TIMELINE_ORIGIN) / 2;
  zoomTimeline(5, pointer);
  const state = useTimeline.getState();
  expect((state.scroll + pointer - TIMELINE_ORIGIN) / state.scale).toBe(frame);
  expect(state.fitting).toBe(false);
});
