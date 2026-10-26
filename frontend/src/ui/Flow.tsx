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
  Scissors,
  Trash2,
  ChevronsLeft,
  Layers,
  MousePointer2,
} from "lucide-react";
import {
  clone,
  detach,
  duration,
  fps,
  layout,
  move,
  pack,
  occupied,
  partners,
  remove,
  split,
  timecode,
  trim,
  trimAudio,
  type Clip,
  type Document,
} from "../model";
import { useTimeline, useTimelineWheel } from "../timeline";
import { useEditor } from "../store";
import { Waveform } from "./Waveform";

export function Flow() {
  const state = useEditor(),
    { project, document, selected, focus, frame, set, save, busy } = state;
  const scroll = useRef<HTMLDivElement>(null),
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
  const { scale: px, scroll: sharedScroll, set: setTimeline } = useTimeline();
  useTimelineWheel(scroll);
  useEffect(() => {
    if (
      scroll.current &&
      Math.abs(scroll.current.scrollLeft - sharedScroll) > 1
    )
      scroll.current.scrollLeft = sharedScroll;
  }, [sharedScroll, px]);
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
  const width = Math.max(
    viewport.width,
    112 +
      Math.max(resolved.total, ...base.clips.map((c) => occupied(c)[1])) * px,
  );
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
      </div>
      <div
        className={`flow-scroll ${dragging ? "dragging" : ""}`}
        ref={scroll}
        onScroll={(e) => setTimeline({ scroll: e.currentTarget.scrollLeft })}
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
          {dragging &&
            [
              ...new Set(
                base.clips
                  .filter(
                    (c) =>
                      c.id === selected ||
                      (!!selectedClip?.linkId &&
                        c.linkId === selectedClip.linkId),
                  )
                  .flatMap((c) => [c.start, c.start + duration(c)])
                  .filter((edge) =>
                    base.clips.some(
                      (c) =>
                        c.id !== selected &&
                        (!selectedClip?.linkId ||
                          c.linkId !== selectedClip.linkId) &&
                        (c.start === edge || c.start + duration(c) === edge),
                    ),
                  ),
              ),
            ].map((edge) => (
              <div
                key={edge}
                className="alignment-guide"
                style={{ left: 56 + edge * px, height: layers * 112 + 40 }}
              />
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
                {isSelected &&
                  kind === "audio" &&
                  (["in", "out"] as const).map((edge) => (
                    <div
                      key={edge}
                      className={`audio-trim-handle trim-${edge}`}
                      title="Trim audio"
                      aria-label={`${edge} audio trim`}
                      onPointerDown={(e) => {
                        e.stopPropagation();
                        e.preventDefault();
                        startTrim(e, c, edge, false);
                      }}
                    />
                  ))}
                {isSelected &&
                  kind !== "audio" &&
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
          {!doc.clips.length && (
            <div className="flow-empty">
              <div className="empty-node">
                <Film size={21} />
                <span>Video</span>
                <div>
                  <Music2 size={13} /> Audio
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
          <MousePointer2 size={12} />
          Double-click a clip to edit <i />
          Ctrl + wheel to zoom <i /> Shift + wheel to scroll
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
    const limit =
      c.sourceOut +
      Math.min(
        ...partners(original, c.id).map(
          (p) =>
            Math.round(
              ((project?.assets.find((a) => a.id === p.assetId)?.probe
                .durationUs ?? 1e12) *
                rate) /
                1e6,
            ) - p.sourceOut,
        ),
      );
    setDragging(true);
    const motion = (event: PointerEvent) => {
      latest = (
        c.kind === "audio"
          ? trimAudio
          : (
              doc: Document,
              id: string,
              edge: "in" | "out",
              delta: number,
              limit: number,
            ) => trim(doc, id, edge, delta, ripple, limit)
      )(original, c.id, edge, (event.clientX - initialX) / px, limit);
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
