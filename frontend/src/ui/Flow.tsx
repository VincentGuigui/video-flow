import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type PointerEvent as ReactPointerEvent,
} from "react";
import {
  Film,
  Music2,
  Link2,
  Unlink,
  Scissors,
  Trash2,
  ChevronsLeft,
  Layers,
  MousePointer2,
  ZoomIn,
  ZoomOut,
  Focus,
} from "lucide-react";
import {
  clone,
  detach,
  duration,
  fps,
  layout,
  move,
  pack,
  partners,
  remove,
  split,
  timecode,
  trim,
  zoomAt,
  type Clip,
  type Document,
} from "../model";
import { useEditor } from "../store";
import { Waveform } from "./Waveform";

export function Flow() {
  const state = useEditor(),
    { project, document, selected, focus, frame, set, save, busy } = state;
  const scroll = useRef<HTMLDivElement>(null),
    [zoom, setZoom] = useState(1),
    [draft, setDraft] = useState<Document | null>(null),
    [dragging, setDragging] = useState(false),
    [viewport, setViewport] = useState({
      left: 0,
      top: 0,
      width: 1200,
      height: 500,
    });
  const doc = draft ?? document;
  const base = useMemo(() => pack(doc), [doc]),
    resolved = useMemo(() => layout(doc), [doc]),
    rate = project ? fps(project.settings) : 30;
  const px = 2 * zoom;
  const layers = Math.max(2, ...doc.clips.map((c) => c.layer + 1));
  useEffect(() => {
    const node = scroll.current;
    if (!node) return;
    let raf = 0;
    const measure = () => {
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(() =>
        setViewport({
          left: node.scrollLeft,
          top: node.scrollTop,
          width: node.clientWidth,
          height: node.clientHeight,
        }),
      );
    };
    const observer = new ResizeObserver(measure);
    observer.observe(node);
    node.addEventListener("scroll", measure);
    measure();
    return () => {
      cancelAnimationFrame(raf);
      observer.disconnect();
      node.removeEventListener("scroll", measure);
    };
  }, []);
  const visible = (c: Clip) =>
    56 + (c.start + duration(c)) * px >= viewport.left - 180 &&
    56 + c.start * px <= viewport.left + viewport.width + 180 &&
    48 + (layers - 1 - c.layer) * 112 >= viewport.top - 180 &&
    48 + (layers - 1 - c.layer) * 112 <= viewport.top + viewport.height + 180;
  const selectedClip = base.clips.find((c) => c.id === selected);
  const focused = base.clips.find((c) => c.id === focus);
  const focusStart = focused
    ? Math.max(0, focused.start - Math.round(rate * 2))
    : 0;
  const focusEnd = focused
    ? Math.min(
        resolved.total,
        focused.start + duration(focused) + Math.round(rate * 2),
      )
    : resolved.total;
  const width = Math.max(
    1000,
    (Math.max(resolved.total, Math.round(rate * 20)) + Math.round(rate * 3)) *
      px,
  );
  useEffect(() => {
    if (!focused || !scroll.current) return;
    const view = scroll.current;
    const newZoom = Math.max(
      0.15,
      Math.min(
        12,
        (view.clientWidth - 120) / Math.max(1, focusEnd - focusStart) / 2,
      ),
    );
    setZoom(newZoom);
    requestAnimationFrame(() => {
      view.scrollLeft = Math.max(0, focusStart * 2 * newZoom - 30);
    });
    // Focus changes, not cursor or each draft gesture, should fit the clip.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focus]);
  function apply(next: Document) {
    setDraft(null);
    void save(next);
  }
  function startGesture(
    e: ReactPointerEvent,
    c: Clip,
    edge?: "in" | "out",
    ripple = false,
  ) {
    if (busy || e.button !== 0) return;
    e.stopPropagation();
    if ((e.target as HTMLElement).closest("button,input")) return;
    e.preventDefault();
    set({ selected: c.id, playing: false });
    const initialX = e.clientX,
      initialY = e.clientY,
      original = pack(document);
    let next = original;
    setDragging(true);
    const maxFrames =
      Math.round(
        ((project?.assets.find((a) => a.id === c.assetId)?.probe.durationUs ??
          0) *
          rate) /
          1e6,
      ) || duration(c);
    const onMove = (event: PointerEvent) => {
      const delta = Math.round((event.clientX - initialX) / px);
      next = edge
        ? trim(original, c.id, edge, delta, ripple, maxFrames)
        : move(
            original,
            c.id,
            c.start + delta,
            Math.max(0, c.layer - Math.round((event.clientY - initialY) / 112)),
          );
      setDraft(next);
    };
    const end = () => {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", end);
      setDragging(false);
      setDraft(null);
      if (JSON.stringify(next) !== JSON.stringify(original)) void save(next);
    };
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", end, { once: true });
  }
  const wheel = (event: WheelEvent) => {
    if (!event.ctrlKey || !scroll.current) return;
    event.preventDefault();
    const container = scroll.current,
      pointer = event.clientX - container.getBoundingClientRect().left;
    setZoom((old) => {
      const next = Math.max(
        0.08,
        Math.min(16, old * Math.exp(-event.deltaY * 0.002)),
      );
      const left = zoomAt(old, next, container.scrollLeft, pointer - 56);
      requestAnimationFrame(() => (container.scrollLeft = Math.max(0, left)));
      return next;
    });
  };
  useEffect(() => {
    const node = scroll.current;
    if (!node) return;
    node.addEventListener("wheel", wheel, { passive: false });
    return () => node.removeEventListener("wheel", wheel);
  }, []);
  const zoomButton = (factor: number) => {
    const container = scroll.current;
    if (!container) return;
    const pointer = container.clientWidth / 2;
    setZoom((old) => {
      const next = Math.max(0.08, Math.min(16, old * factor));
      const left = zoomAt(old, next, container.scrollLeft, pointer - 56);
      requestAnimationFrame(() => (container.scrollLeft = left));
      return next;
    });
  };
  const ticks: number[] = [];
  const step =
    [1, 2, 5, 10, 15, 30, 60, 120, 300].find((s) => s * rate * px > 70) ?? 600;
  for (
    let second = Math.max(
      0,
      Math.floor((viewport.left - 56) / px / rate / step) * step,
    );
    second <= Math.min(width, viewport.left + viewport.width + 180) / px / rate;
    second += step
  )
    ticks.push(second);
  const pairs = useMemo(
    () => base.clips.filter((c) => c.kind !== "audio" || !c.linkId),
    [base],
  );
  const actualIds = new Set(resolved.clips.map((c) => c.id));
  return (
    <section className="flow-panel">
      <div className="flow-toolbar">
        <div className="flow-heading">
          
          <strong>Clip flow</strong>
          <span className="count-badge">{pairs.length} clips</span>
        </div>
        <div className="clip-actions">
          <button
            disabled={!selectedClip || busy}
            onClick={() =>
              selectedClip &&
              apply(split(pack(document), selectedClip.id, frame))
            }
            title="Split at cursor (S)"
          >
            <Scissors size={14} />
            Split
          </button>
          <button
            disabled={!selectedClip || busy}
            onClick={() =>
              selectedClip &&
              apply(remove(pack(document), selectedClip.id, false))
            }
            title="Lift: replace with empty clip (Delete)"
          >
            <Trash2 size={14} />
            Lift
          </button>
          <button
            disabled={!selectedClip || busy}
            onClick={() =>
              selectedClip &&
              apply(remove(pack(document), selectedClip.id, true))
            }
            title="Ripple delete (Backspace)"
          >
            <ChevronsLeft size={14} />
            Ripple
          </button>
        </div>
        <div className="zoom-controls">
          <button
            className="icon-button"
            title="Zoom out"
            onClick={() => zoomButton(0.8)}
          >
            <ZoomOut size={15} />
          </button>
          <span>{Math.round(zoom * 100)}%</span>
          <button
            className="icon-button"
            title="Zoom in"
            onClick={() => zoomButton(1.25)}
          >
            <ZoomIn size={15} />
          </button>
          <button
            className="icon-button"
            title="Fit assembly"
            onClick={() => {
              setZoom(
                Math.max(
                  0.08,
                  Math.min(
                    16,
                    ((scroll.current?.clientWidth ?? 1000) - 150) /
                      Math.max(1, resolved.total) /
                      2,
                  ),
                ),
              );
              if (scroll.current) scroll.current.scrollLeft = 0;
              set({ focus: null });
            }}
          >
            <Focus size={15} />
          </button>
        </div>
      </div>
      {focus && (
        <div className="focus-banner">
          <Focus size={13} />
          Editing {selectedClip?.name ?? focused?.name}
          <span>
            {timecode(focusStart, rate)} — {timecode(focusEnd, rate)}
          </span>
          <button onClick={() => set({ focus: null, selected: null })}>
            Back to full edit <kbd>Esc</kbd>
          </button>
        </div>
      )}
      <div
        className={`flow-scroll ${dragging ? "dragging" : ""}`}
        ref={scroll}
        data-testid="flow"
        onDoubleClick={(e) => {
          if (!(e.target as HTMLElement).closest(".clip-card"))
            set({ selected: null, focus: null });
        }}
      >
        <div
          className="flow-canvas"
          style={{ width, height: Math.max(300, layers * 112 + 58) }}
          onPointerDown={(e) => {
            if (e.target === e.currentTarget) set({ selected: null });
          }}
        >
          <div className="flow-ruler">
            {ticks.map((s) => (
              <span key={s} style={{ left: s * rate * px + 56 }}>
                {s < 60
                  ? `${s}s`
                  : `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`}
              </span>
            ))}
          </div>
          {Array.from({ length: layers }, (_, i) => (
            <div
              key={i}
              className="layer-line"
              style={{ top: 48 + (layers - 1 - i) * 112 }}
            >
              <span>
                <Layers size={11} />
                {i + 1}
              </span>
            </div>
          ))}
          {dragging && [...new Set(base.clips.filter(c => c.id === selected || (!!selectedClip?.linkId && c.linkId === selectedClip.linkId)).flatMap(c => [c.start,c.start+duration(c)])
            .filter(edge => base.clips.some(c => c.id !== selected && (!selectedClip?.linkId || c.linkId !== selectedClip.linkId) && (c.start === edge || c.start+duration(c) === edge))))].map(edge => (
            <div key={edge} className="alignment-guide" style={{left:56+edge*px,height:layers*112+40}} />
          ))}
          {base.clips.filter(visible).map((c) => {
            const linked = !!c.linkId,
              kind = c.kind;
            const y =
              48 + (layers - 1 - c.layer) * 112 + (kind === "audio" ? 53 : 0);
            const w = Math.max(18, duration(c) * px - 5),
              isSelected =
                c.id === selected ||
                (!!selectedClip?.linkId && selectedClip.linkId === c.linkId);
            const opacity = c.enabled && actualIds.has(c.id) ? 1 : 0.42;
            return (
              <div
                key={c.id}
                data-testid={`clip-${kind}`}
                data-clip-id={c.id}
                className={`clip-card ${kind} ${isSelected ? "selected" : ""}`}
                style={{
                  left: 56 + c.start * px,
                  top: y,
                  width: w,
                  height: kind === "audio" ? 31 : 50,
                  opacity,
                  zIndex: isSelected ? 8 : 3,
                }}
                onPointerDown={(e) => startGesture(e, c)}
                onClick={(e) => {
                  e.stopPropagation();
                  set({ selected: c.id });
                }}
                onDoubleClick={(e) => {
                  e.stopPropagation();
                  set({
                    selected: c.id,
                    focus: c.id,
                    frame: c.start,
                    playing: false,
                  });
                }}
              >
                <div className="clip-topline">
                  {kind === "audio" ? (
                    <Music2 size={12} />
                  ) : kind === "video" ? (
                    <Film size={13} />
                  ) : (
                    <span className="gap-icon" />
                  )}
                  <span className="clip-name">{c.name}</span>
                  <input
                    aria-label={`Enable ${kind} ${c.name}`}
                    type="checkbox"
                    checked={c.enabled}
                    onPointerDown={(e) => e.stopPropagation()}
                    onChange={(e) => {
                      const next = clone(document);
                      next.clips.find((p) => p.id === c.id)!.enabled =
                        e.target.checked;
                      apply(next);
                    }}
                  />
                </div>
                {kind === "video" && (
                  <div className="clip-detail">
                    {timecode(duration(c), rate)}
                    <span>{linked ? "Linked audio" : "Video"}</span>
                  </div>
                )}
                {kind === "audio" && <Waveform clip={c} rate={rate} />}
                {kind === "gap" && (
                  <div className="clip-detail">
                    Black / silence · {timecode(duration(c), rate)}
                  </div>
                )}
                {linked && kind === "video" && (
                  <button
                    className="chain-button"
                    title="Detach audio and video"
                    aria-label={`Detach ${c.name}`}
                    onPointerDown={(e) => e.stopPropagation()}
                    onClick={(e) => {
                      e.stopPropagation();
                      apply(detach(document, c.id));
                    }}
                  >
                    <Link2 size={13} />
                  </button>
                )}
                {!linked && kind !== "gap" && isSelected && (
                  <span className="detached-label" title="Independent clip">
                    <Unlink size={10} />
                  </span>
                )}
                {isSelected &&
                  (["in", "out"] as const).map((edge) => (
                    <div className={`trim-handles trim-${edge}`} key={edge}>
                      <span
                        title={`${edge === "in" ? "Head" : "Tail"} ripple trim — changes total duration`}
                        aria-label={`${edge} ripple trim`}
                        onPointerDown={(e) => {
                          e.stopPropagation();
                          e.preventDefault();
                          startTrim(e, c, edge, true);
                        }}
                      />
                      <span
                        title={`${edge === "in" ? "Head" : "Tail"} preserve-time trim — adds empty clip`}
                        aria-label={`${edge} preserve trim`}
                        onPointerDown={(e) => {
                          e.stopPropagation();
                          e.preventDefault();
                          startTrim(e, c, edge, false);
                        }}
                      />
                    </div>
                  ))}
              </div>
            );
          })}
          <div
            className="flow-playhead"
            style={{ left: 56 + frame * px, height: layers * 112 + 40 }}
            onPointerDown={(e) => {
              e.preventDefault();
              e.stopPropagation();
              const node = scroll.current;
              if (!node) return;
              const seek = (client: number) =>
                set({
                  frame: Math.max(
                    0,
                    Math.min(
                      resolved.total - 1,
                      Math.round(
                        (client -
                          node.getBoundingClientRect().left +
                          node.scrollLeft -
                          56) /
                          px,
                      ),
                    ),
                  ),
                  playing: false,
                });
              const motion = (e: PointerEvent) => seek(e.clientX);
              const end = () =>
                window.removeEventListener("pointermove", motion);
              window.addEventListener("pointermove", motion);
              window.addEventListener("pointerup", end, { once: true });
            }}
          >
            <span />
          </div>
          {!doc.clips.length && (
            <div className="flow-empty">
              <div className="empty-node">
                <Film size={21} />
                <span>Video</span>
                <div>
                  <Music2 size={13} /> Linked audio
                </div>
              </div>
              <div>
                <h2>Your story, connected.</h2>
                <p>
                  Drop video or audio here. Build a sequence,
                  <br />
                  compare takes, and find your flow.
                </p>

              </div>
            </div>
          )}
        </div>
      </div>
      <div className="flow-footer">
        <span>
          <span className="legend-dot video" />
          Video
          <span className="legend-dot audio" />
          Audio
          <span className="legend-dot enabled" />
          Enabled
        </span>
        <span>
          <MousePointer2 size={12} />
          Double-click a clip to edit <i />
          Ctrl + wheel to zoom
        </span>
      </div>
    </section>
  );

  function startTrim(
    e: ReactPointerEvent,
    c: Clip,
    edge: "in" | "out",
    ripple: boolean,
  ) {
    // Handle children are outside the card's draggable hit target.
    if (busy) return;
    const original = pack(document),
      initialX = e.clientX;
    let latest = original;
    const limit = Math.round(
      ((project?.assets.find((a) => a.id === c.assetId)?.probe.durationUs ??
        1e12) *
        rate) /
        1e6,
    );
    setDragging(true);
    const motion = (event: PointerEvent) => {
      latest = trim(
        original,
        c.id,
        edge,
        (event.clientX - initialX) / px,
        ripple,
        limit,
      );
      setDraft(latest);
    };
    const end = () => {
      window.removeEventListener("pointermove", motion);
      window.removeEventListener("pointerup", end);
      setDragging(false);
      apply(latest);
    };
    window.addEventListener("pointermove", motion);
    window.addEventListener("pointerup", end, { once: true });
  }
}
