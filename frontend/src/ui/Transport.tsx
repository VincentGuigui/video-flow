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
import {
  keyframeOffsets,
  moveKeyframe,
  sourceAt,
  timelineAt,
} from "../keyframes";
import { currentRange, togglePlay } from "../playback";
import { defaultRange, moveHandle, type Handle } from "../range";
import {
  activeDuration,
  activeTransitions,
  sourceFramesFor,
  TRANSITION_LABELS,
  cutKey,
} from "../transitions";

export function Transport() {
  const { project, document, frame, focus, rangeHandle, set } =
    useEditor();
  const zone = useEditor((s) => s.zone),
    selectedClips = useEditor((s) => s.selectedClips);
  const range = currentRange();
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
  function grab(handle: Handle, event: ReactPointerEvent) {
    event.preventDefault();
    event.stopPropagation();
    const node = root.current;
    if (!node) return;
    set({ rangeHandle: handle, playing: false });
    const position = (x: number) =>
      (x - node.getBoundingClientRect().left + node.scrollLeft - origin) /
      scale;
    const motion = (e: PointerEvent) =>
      set({
        range: moveHandle(currentRange(), handle, position(e.clientX), total),
      });
    const end = () => window.removeEventListener("pointermove", motion);
    window.addEventListener("pointermove", motion);
    window.addEventListener("pointerup", end, { once: true });
  }
  function scrub(event: ReactPointerEvent) {
    event.preventDefault();
    if (rangeHandle) set({ rangeHandle: null });
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
    <section
      className={`transport-panel ${zone === "timeline" ? "zone-active" : ""}`}
      onPointerDownCapture={() =>
        useEditor.getState().set({ zone: "timeline" })
      }
    >
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
                  onDoubleClick={(e) => {
                    e.stopPropagation();
                    set({ selected: c.id, focus: c.id, frame: c.start, playing: false });
                  }}
                  title={c.name}
                  className={`overview-clip ${c.kind} ${selectedClips.includes(c.id) ? "selected" : ""}`}
                  style={{
                    left: origin + c.start * scale,
                    width: Math.max(1, duration(c) * scale - 2),
                    height: Math.max(7, 28 - c.layer * 4),
                    bottom: c.layer * 4,
                  }}
                />
              ))}
          </div>
          {activeTransitions(document, sourceFramesFor(project)).map((a) => (
            <div
              key={a.transition.id}
              className={`overview-transition ${a.transition.type}`}
              data-testid="timeline-transition"
              role="button"
              onPointerDown={(e) => e.stopPropagation()}
              onClick={(e) => {
                e.stopPropagation();
                useEditor.getState().set({
                  selected: a.transition.rightId,
                  inspectorTab: "Effects",
                  effectFocus: cutKey(
                    a.transition.leftId,
                    a.transition.rightId,
                  ),
                });
              }}
              title={`${TRANSITION_LABELS[a.transition.type]} · ${(activeDuration(a) / rate).toFixed(2)} s`}
              style={{
                left: origin + (a.cut - a.before) * scale,
                width: Math.max(4, activeDuration(a) * scale),
              }}
            />
          ))}
          <KeyframeLane origin={origin} scale={scale} />
          <div
            className="overview-range"
            data-testid="timeline-range"
            style={{
              left: origin + range.start * scale,
              width: Math.max(1, (range.end - range.start) * scale),
            }}
          />
          {(["start", "end"] as const).map((handle) => (
            <div
              key={handle}
              role="slider"
              aria-label={`Range ${handle}`}
              aria-valuenow={range[handle]}
              title={`Range ${handle} ${timecode(range[handle], rate)}. Drag to move; select and press Space to play around it.`}
              data-testid={`range-${handle}`}
              className={`range-handle ${handle} ${rangeHandle === handle ? "selected" : ""}`}
              style={{ left: origin + range[handle] * scale }}
              onPointerDown={(e) => grab(handle, e)}
            />
          ))}
          <div
            className="overview-playhead"
            style={{ left: origin + frame * scale }}
          >
            <span />
          </div>
        </div>
      </div>

    </section>
  );
}

// Keyframes of the selected video clip on the timeline (docs/features/keyframes.md):
// click to move the cursor there and select it (Delete removes it), drag to move it
// inside the clip's visible range.
function KeyframeLane({ origin, scale }: { origin: number; scale: number }) {
  const { document, selected, save, busy, set } = useEditor();
  const chosen = useEditor((s) => s.keyframe);
  const [moving, setMoving] = useState<{ from: number; to: number } | null>(
    null,
  );
  const clip = layout(document).clips.find(
    (c) => c.id === selected && c.kind === "video",
  );
  if (!clip?.keyframes?.length) return null;
  return (
    <>
      {keyframeOffsets(clip).map(({ frame, offset }) => {
        const shown =
          moving?.from === frame
            ? timelineAt(clip, moving.to)
            : clip.start + offset;
        return (
          <button
            key={frame}
            className={`timeline-keyframe ${chosen === frame ? "selected" : ""}`}
            data-testid="timeline-keyframe"
            aria-label={`Keyframe at ${frame}`}
            title="Keyframe: click to go there, drag to move, Delete to remove"
            style={{ left: origin + shown * scale }}
            disabled={busy}
            onPointerDown={(e) => {
              e.stopPropagation();
              e.preventDefault();
              const x0 = e.clientX,
                position = clip.start + offset;
              let to = frame;
              set({ frame: position, playing: false, keyframe: frame });
              const motion = (event: PointerEvent) => {
                const target = Math.min(
                  clip.start + duration(clip) - 1,
                  Math.max(
                    clip.start,
                    position + Math.round((event.clientX - x0) / scale),
                  ),
                );
                to = sourceAt(clip, target);
                setMoving({ from: frame, to });
                set({ frame: target });
              };
              const end = () => {
                window.removeEventListener("pointermove", motion);
                setMoving(null);
                if (to !== frame) {
                  const next = moveKeyframe(document, clip.id, frame, to);
                  if (next !== document) {
                    void save(next);
                    set({ keyframe: to });
                  }
                }
              };
              window.addEventListener("pointermove", motion);
              window.addEventListener("pointerup", end, { once: true });
            }}
          />
        );
      })}
    </>
  );
}


export function PlaybackControls() {
  const {project,document,frame,playing,focus,set} = useEditor();
  const rate = project ? fps(project.settings) : 30;
  const total = layout(document).total;
  const {start,end} = defaultRange(document,focus,rate);
  const seek = (value:number) => set({frame:Math.max(start,Math.min(Math.max(start,end-1),Math.round(value))),playing:false});
  return (
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
            onClick={togglePlay}
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
          <kbd>Space</kbd> plays the range <i /> Drag the cursor to scrub
        </span>
      </div>
  );
}
