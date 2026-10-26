import { fps, layout } from "./model";
import { defaultRange, playStart, playWindow, type Range } from "./range";
import { useEditor } from "./store";

export function currentRange(): Range {
  const s = useEditor.getState(),
    rate = s.project ? fps(s.project.settings) : 30,
    total = layout(s.document).total;
  const range = s.range ?? defaultRange(s.document, s.focus, rate);
  return {
    start: Math.max(0, Math.min(total, range.start)),
    end: Math.max(0, Math.min(total, range.end)),
  };
}

export function currentWindow(): Range {
  const s = useEditor.getState(),
    rate = s.project ? fps(s.project.settings) : 30;
  return playWindow(
    currentRange(),
    s.rangeHandle,
    rate,
    layout(s.document).total,
  );
}

// Space and the play button: play the range (or the window around the selected
// handle) once; stopping returns the cursor to the window start.
export function togglePlay() {
  const s = useEditor.getState();
  if (s.playing) return s.set({ playing: false });
  const window = currentWindow();
  if (window.end - window.start < 1) return;
  s.set({ playing: true, frame: playStart(window, s.frame) });
}
