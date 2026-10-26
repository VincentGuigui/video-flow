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
  CornerDownLeft,
} from "lucide-react";
import { duration, fps, layout, timecode, zoomAt } from "../model";
import { useEditor } from "../store";

export function Transport() {
  const { project, document, frame, playing, focus, set } = useEditor();
  const root = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(1000),
    [zoom, setZoom] = useState(1);
  const resolved = layout(document),
    rate = project ? fps(project.settings) : 30,
    total = resolved.total;
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
      setWidth(entry.contentRect.width),
    );
    observer.observe(root.current);
    return () => observer.disconnect();
  }, []);
  useEffect(() => {
    const node = root.current;
    if (!node) return;
    const wheel = (e: WheelEvent) => {
      if (e.shiftKey && !e.ctrlKey) {
        e.preventDefault();
        node.scrollLeft += e.deltaY || e.deltaX;
        return;
      }
      if (!e.ctrlKey) return;
      e.preventDefault();
      const pointer = e.clientX - node.getBoundingClientRect().left;
      setZoom((old) => {
        const next = Math.min(
          40,
          Math.max(1, old * Math.exp(-e.deltaY * 0.002)),
        );
        const left = zoomAt(old, next, node.scrollLeft, pointer);
        requestAnimationFrame(() => (node.scrollLeft = left));
        return next;
      });
    };
    node.addEventListener("wheel", wheel, { passive: false });
    return () => node.removeEventListener("wheel", wheel);
  }, []);
  const scale = (width * zoom) / Math.max(total, Math.round(rate * 10));
  useEffect(() => {
    const node = root.current;
    if (!node || width <= 0) return;
    if (!focus) {
      setZoom(1);
      node.scrollLeft = 0;
      return;
    }
    const span = Math.max(1, end - start);
    setZoom(Math.max(1, Math.max(total, Math.round(rate * 10)) / span));
    requestAnimationFrame(() => {
      node.scrollLeft = (start * width) / span;
    });
    // Refit on focus or viewport changes; ordinary cursor changes retain zoom.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focus, width]);
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
      (x - node.getBoundingClientRect().left + node.scrollLeft) / scale;
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
  for (let t = 0; t <= Math.max(total, rate * 10) / rate; t += step)
    ticks.push(t);
  return (
    <section className="transport-panel">
      <div className="transport-heading">
        <span> {focus ? "Clip timeline" : "Assembly timeline"}</span>
        <span className="transport-time">
          <strong data-testid="timecode">{timecode(frame, rate)}</strong>
          <span>/ {timecode(total, rate)}</span>
        </span>
        <span className="muted">Drag the cursor to scrub</span>
      </div>
      <div
        className="overview-scroll"
        ref={root}
        onPointerDown={scrub}
        data-testid="timeline"
      >
        <div
          className="overview-content"
          style={{ width: Math.max(width, Math.max(total, rate * 10) * scale) }}
        >
          <div className="overview-ruler">
            {ticks.map((t) => (
              <span key={t} style={{ left: t * rate * scale }}>
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
                    left: c.start * scale,
                    width: Math.max(1, duration(c) * scale - 2),
                    height: Math.max(7, 28 - c.layer * 4),
                    bottom: c.layer * 4,
                  }}
                />
              ))}
          </div>
          <div className="overview-playhead" style={{ left: frame * scale }}>
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
          <kbd>Space</kbd> to play / pause
        </span>
      </div>
    </section>
  );
}
