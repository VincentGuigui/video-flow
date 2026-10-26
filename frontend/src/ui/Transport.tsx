import {
  useEffect,
  useRef,
  useState,
  type PointerEvent as ReactPointerEvent,
} from "react";
import {
  SkipBack,
  SkipForward,
  Play,
  Pause,
  ChevronLeft,
  ChevronRight,
  ChevronsLeft,
  ChevronsRight,
  ZoomIn,
  ZoomOut,
  Focus,
} from "lucide-react";
import { duration, fps, layout, pack, occupied, timecode } from "../model";
import {
  useTimeline,
  useTimelineWheel,
  zoomTimeline,
  TIMELINE_ORIGIN as origin,
} from "../timeline";
import { useEditor } from "../store";

export function Transport() {
  const { project, document, frame, highlight, playing, focus, set } =
    useEditor();
  const root = useRef<HTMLDivElement>(null);
  const { scale, scroll, width, set: setTimeline } = useTimeline();
  const previousFocus = useRef<string | null | undefined>(undefined);
  useTimelineWheel(root);
  const resolved = layout(document),
    rate = project ? fps(project.settings) : 30,
    total = resolved.total;
  const extent = Math.max(
    total,
    ...pack(document).clips.map((c) => occupied(c)[1]),
  );
  const fitSpan = total || extent || Math.round(rate * 10);
  const selected = resolved.clips.find((c) => c.id === focus),
    start = selected ? Math.max(0, selected.start - Math.round(rate * 2)) : 0,
    end = selected
      ? Math.min(
          total,
          selected.start + duration(selected) + Math.round(rate * 2),
        )
      : total;
  useEffect(() => {
    if (!root.current) return;
    const observer = new ResizeObserver(([entry]) =>
      setTimeline({ width: entry.contentRect.width }),
    );
    observer.observe(root.current);
    return () => observer.disconnect();
  }, []);
  function fitRange() {
    const next = Math.max(
      0.001,
      (width - origin * 2) / Math.max(1, end - start || fitSpan),
    );
    setTimeline({
      scale: next,
      scroll: Math.max(0, start * next),
      fitting: true,
    });
  }
  useEffect(() => {
    const changed = previousFocus.current !== focus;
    previousFocus.current = focus;
    if (changed || useTimeline.getState().fitting) fitRange();
  }, [focus, width, total, extent]);
  useEffect(() => {
    if (root.current && Math.abs(root.current.scrollLeft - scroll) > 1)
      root.current.scrollLeft = scroll;
  }, [scroll, scale]);
  function seek(value: number) {
    set({
      frame: Math.max(
        start,
        Math.min(Math.max(start, end - 1), Math.round(value)),
      ),
      playing: false,
    });
  }
  function scrub(event: ReactPointerEvent) {
    event.preventDefault();
    const node = root.current;
    if (!node) return;
    const position = (x: number) =>
      (x - node.getBoundingClientRect().left + node.scrollLeft - origin) /
      scale;
    seek(position(event.clientX));
    const motion = (e: PointerEvent) => seek(position(e.clientX));
    const end = () => window.removeEventListener("pointermove", motion);
    window.addEventListener("pointermove", motion);
    window.addEventListener("pointerup", end, { once: true });
  }
  const step = Math.max(
      1,
      [1, 2, 5, 10, 15, 30, 60, 120, 300].find((s) => s * rate * scale > 85) ??
        600,
    ),
    ticks = [];
  for (
    let t = Math.max(
      0,
      Math.floor((scroll - origin) / scale / rate / step) * step,
    );
    t <=
    Math.min(Math.max(total, extent) / rate, (scroll + width) / scale / rate);
    t += step
  )
    ticks.push(t);
  return (
    <section className="transport-panel">
      <div className="transport-heading">
        <span>
          {focus ? "Clip timeline" : "Assembly timeline"}
          {focus && (
            <button
              className="exit-focus"
              onClick={() => set({ focus: null, selected: null })}
            >
              Back to full edit <kbd>Esc</kbd>
            </button>
          )}
        </span>
        <span className="transport-time">
          <strong data-testid="timecode">{timecode(frame, rate)}</strong>
          <span>/ {timecode(total, rate)}</span>
        </span>
        <div className="zoom-controls">
          <button
            className="icon-button"
            aria-label="Zoom out timeline"
            title="Zoom out"
            onClick={() => zoomTimeline(scale * 0.8, width / 2)}
          >
            <ZoomOut size={15} />
          </button>
          <span>
            {Math.round(
              (scale /
                Math.max(0.001, (width - origin * 2) / Math.max(1, fitSpan))) *
                100,
            )}
            %
          </span>
          <button
            className="icon-button"
            aria-label="Zoom in timeline"
            title="Zoom in"
            onClick={() => zoomTimeline(scale * 1.25, width / 2)}
          >
            <ZoomIn size={15} />
          </button>
          <button
            className="icon-button"
            title={focus ? "Fit clip range" : "Fit assembly"}
            onClick={fitRange}
          >
            <Focus size={15} />
          </button>
        </div>
      </div>
      <div
        className="overview-scroll"
        ref={root}
        onScroll={(e) => setTimeline({ scroll: e.currentTarget.scrollLeft })}
        onPointerDown={scrub}
        data-testid="timeline"
      >
        <div
          className="overview-content"
          style={{
            width: Math.max(
              width,
              origin * 2 + Math.max(extent, total) * scale,
            ),
          }}
        >
          <div className="overview-ruler">
            {ticks.map((t) => (
              <span key={t} style={{ left: origin + t * rate * scale }}>
                {timecode(t * rate, rate).slice(3, 8)}
              </span>
            ))}
          </div>
          <div className="overview-track">
            {resolved.clips
              .filter((c) => c.kind !== "audio" || !c.linkId)
              .map((c) => (
                <div
                  key={c.id}
                  title={c.name}
                  className={`overview-clip ${c.kind}`}
                  style={{
                    left: origin + c.start * scale,
                    width: Math.max(1, duration(c) * scale - 2),
                    height: Math.max(7, 28 - c.layer * 4),
                    bottom: c.layer * 4,
                  }}
                />
              ))}
          </div>
          {highlight && (
            <div
              className="overview-highlight"
              data-testid="timeline-highlight"
              style={{
                left: origin + highlight.start * scale,
                width: Math.max(2, (highlight.end - highlight.start) * scale),
              }}
            />
          )}
          <div
            className="overview-playhead"
            style={{ left: origin + frame * scale }}
          >
            <span />
          </div>
        </div>
      </div>
      <div className="transport-buttons">
        <div className="navigation">
          <button title="Beginning (Home)" onClick={() => seek(start)}>
            <SkipBack size={16} />
          </button>
          <button
            title="Back 10 seconds (Ctrl + Left)"
            onClick={() => seek(frame - rate * 10)}
          >
            <ChevronsLeft size={15} />
            <small>10s</small>
          </button>
          <button
            title="Back 1 second (Shift + Left)"
            onClick={() => seek(frame - rate)}
          >
            <ChevronLeft size={15} />
            <small>1s</small>
          </button>
          <button title="Previous frame (Left)" onClick={() => seek(frame - 1)}>
            <ChevronLeft size={15} />
            <small>1f</small>
          </button>
          <button
            className="play-button"
            aria-label={playing ? "Pause" : "Play"}
            disabled={!total}
            onClick={() =>
              set({
                playing: !playing,
                frame: frame >= end - 1 ? start : frame,
              })
            }
          >
            {playing ? (
              <Pause size={18} />
            ) : (
              <Play size={18} fill="currentColor" />
            )}
          </button>
          <button title="Next frame (Right)" onClick={() => seek(frame + 1)}>
            <small>1f</small>
            <ChevronRight size={15} />
          </button>
          <button
            title="Forward 1 second (Shift + Right)"
            onClick={() => seek(frame + rate)}
          >
            <small>1s</small>
            <ChevronRight size={15} />
          </button>
          <button
            title="Forward 10 seconds (Ctrl + Right)"
            onClick={() => seek(frame + rate * 10)}
          >
            <small>10s</small>
            <ChevronsRight size={15} />
          </button>
          <button title="End (End)" onClick={() => seek(end - 1)}>
            <SkipForward size={16} />
          </button>
        </div>
        <span className="transport-space">
          <kbd>Space</kbd> to play / pause <i /> Drag the cursor to scrub
        </span>
      </div>
    </section>
  );
}
