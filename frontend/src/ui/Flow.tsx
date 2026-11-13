import { stackedTakes } from "../compare";
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
  Type,
  PanelBottom,
  Blend,
  Plus,
  Image as ImageIcon,
  Snowflake,
} from "lucide-react";
import {
  clone,
  detach,
  duration,
  fps,
  freezeAtCursor,
  isStill,
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
import { autoTrim, trimToRange, removeRange } from "../range";
import { currentRange } from "../playback";
import { useTimeline, useTimelineWheel } from "../timeline";
import { addTitle, type Title } from "../titles";
import { useEditor } from "../store";
import { cutKey, cuts, transitionAt, TRANSITION_LABELS } from "../transitions";
import { keyframeOffsets } from "../keyframes";
import { clipTip } from "../clipTip";
import { hitMarks, useSearch } from "../search";
import { useAnalyses } from "./useAnalysis";
import { Waveform } from "./Waveform";

export function Flow() {
  const zone = useEditor((s) => s.zone);
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
  // Tooltips describe each clip with the analysis of its source (not for pictures).
  const sources = useMemo(
    () => [
      ...new Set(
        base.clips
          .filter(
            (c) => (c.kind === "video" || c.kind === "audio") && c.assetId,
          )
          .filter(
            (c) =>
              !project?.assets.find((a) => a.id === c.assetId)?.probe.still,
          )
          .map((c) => c.assetId!),
      ),
    ],
    [base, project?.assets],
  );
  const analyses = useAnalyses(sources);
  // Occurrences of the text search (docs/features/editing/text-search.md).
  const hits = useSearch((s) => s.hits);
  const marks = useMemo(() => hitMarks(document, hits), [document, hits]);
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
  const takes = selectedClip ? stackedTakes(document, selectedClip.id) : [];
  const selectedAnalysis = analyses[selectedClip?.assetId ?? ""];
  const rangeTrim = selectedClip
    ? trimToRange(document, selectedClip.id, currentRange())
    : null;
  const silenceTrim =
    selectedClip && selectedAnalysis?.words
      ? autoTrim(
          document,
          selectedClip.id,
          selectedAnalysis.words,
          rate,
          project?.settings.clipPadding as
            { beforeUs: number; afterUs: number } | undefined,
        )
      : null;
  const analysis = selectedAnalysis;
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
  const freeze = useMemo(
    () => freezeAtCursor(document, selected, frame, rate),
    [document, selected, frame, rate],
  );
  return (
    <section
      className={`flow-panel ${zone === "flow" ? "zone-active" : ""}`}
      onPointerDownCapture={() => useEditor.getState().set({ zone: "flow" })}
    >
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
          <div
            className="flow-range"
            style={{
              left: 56 + currentRange().start * px,
              width: Math.max(
                1,
                (currentRange().end - currentRange().start) * px,
              ),
            }}
          />
          <div className="flow-cursor" style={{ left: 56 + frame * px }} />
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
            const kind = c.kind;
            const y =
              48 + (layers - 1 - c.layer) * 112 + (kind === "audio" ? 53 : 0);
            const w = Math.max(18, duration(c) * px - 5),
              isSelected =
                c.id === selected ||
                state.selectedClips.includes(c.id) ||
                (!!selectedClip?.linkId && selectedClip.linkId === c.linkId);
            const opacity = c.enabled && actualIds.has(c.id) ? 1 : 0.42;
            return (
              <div
                key={c.id}
                data-testid={`clip-${kind}`}
                data-clip-id={c.id}
                title={clipTip(c, analyses[c.assetId ?? ""])}
                className={`clip-card ${kind} ${isSelected ? "selected" : ""} ${marks.has(c.id) ? "search-hit" : ""}`}
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
                  ) : kind === "video" && isStill(c) ? (
                    <ImageIcon size={13} />
                  ) : kind === "video" ? (
                    <Film size={13} />
                  ) : kind === "text" ? (
                    <Type size={13} />
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
                {(kind === "video" || kind === "text") && (
                  <div className="clip-detail">
                    {kind === "text" &&
                      (c.title?.style === "lower_third"
                        ? "Lower third · "
                        : "Title · ")}
                    {timecode(duration(c), rate)}
                  </div>
                )}
                {kind === "audio" && <Waveform clip={c} rate={rate} />}
                {kind === "gap" && (
                  <div className="clip-detail">
                    Black / silence · {timecode(duration(c), rate)}
                  </div>
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
                {marks.get(c.id)?.map((offset, i) => (
                  <span
                    key={`hit-${i}`}
                    className="flow-search-mark"
                    style={{ left: offset * px }}
                  />
                ))}
                {kind === "video" &&
                  keyframeOffsets(c).map(({ frame: k, offset }) => (
                    <span
                      key={k}
                      className="flow-keyframe"
                      style={{ left: offset * px }}
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
          {!dragging &&
            cuts(doc).map((cut) => {
              const right = base.clips.find((c) => c.id === cut.rightId);
              if (!right) return null;
              const t = transitionAt(doc, cut.leftId, cut.rightId),
                key = cutKey(cut.leftId, cut.rightId);
              return (
                <button
                  key={key}
                  className={`cut-marker ${t ? t.type : "cut"} ${state.effectFocus === key && state.inspectorTab === "Effects" ? "focused" : ""}`}
                  data-testid="cut-marker"
                  aria-label={
                    t ? TRANSITION_LABELS[t.type] : "Cut: add a transition"
                  }
                  title={
                    t
                      ? `${TRANSITION_LABELS[t.type]} · ${(t.duration / rate).toFixed(2)} s`
                      : "Cut · click to choose a transition"
                  }
                  style={{
                    left: 56 + right.start * px - 11,
                    top: 48 + (layers - 1 - right.layer) * 112 + 14,
                  }}
                  onPointerDown={(e) => e.stopPropagation()}
                  onClick={(e) => {
                    e.stopPropagation();
                    set({
                      selected: cut.rightId,
                      inspectorTab: "Effects",
                      effectFocus: key,
                    });
                  }}
                >
                  {t ? <Blend size={11} /> : <Plus size={11} />}
                </button>
              );
            })}
          {/* The link of a video and its audio: in the middle of the pair, above both
              cards so it stays clickable. */}
          {base.clips
            .filter((c) => visible(c) && c.kind === "video" && c.linkId)
            .map((c) => (
              <button
                key={`link-${c.id}`}
                className="chain-button"
                title="Detach audio and video"
                aria-label={`Detach ${c.name}`}
                style={{
                  left:
                    56 + c.start * px + Math.max(18, duration(c) * px - 5) / 2,
                  top: 48 + (layers - 1 - c.layer) * 112 + 41,
                  opacity: c.enabled && actualIds.has(c.id) ? 1 : 0.42,
                }}
                onPointerDown={(e) => e.stopPropagation()}
                onClick={(e) => {
                  e.stopPropagation();
                  apply(detach(document, c.id));
                }}
              >
                <Link2 size={13} />
              </button>
            ))}
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
                  Drop video, audio or images here. Build a sequence,
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
      <div className="flow-toolbar">
        <div className="flow-heading">
          <strong>Clip flow</strong>
          <span className="count-badge">{pairs.length} clips</span>
        </div>
        <div className="clip-actions">
          {takes.length > 1 && (
            <button
              className="button compare-action"
              onClick={() =>
                useEditor
                  .getState()
                  .set({ compare: selectedClip!.id, playing: false })
              }
            >
              <Layers size={14} />
              Compare takes ({takes.length})
            </button>
          )}

          <button
            className="button trim-range-action"
            disabled={busy || !rangeTrim}
            title="Keep only the part of the clip inside the timeline range; later clips move earlier"
            onClick={() => {
              if (!rangeTrim) return;
              apply(rangeTrim);
              useEditor.getState().set({ range: null, rangeHandle: null });
            }}
          >
            <Scissors size={14} />
            Trim clip to range
          </button>
          <button
            className="button auto-trim-action"
            disabled={busy || !silenceTrim}
            title={
              analysis?.words?.length
                ? "Remove silence before the first and after the last word"
                : "Needs a transcript (import with analysis)"
            }
            onClick={() => silenceTrim && apply(silenceTrim)}
          >
            <Scissors size={14} />
            Auto-trim silence
          </button>

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
            disabled={!freeze || busy}
            onClick={() => {
              if (!freeze) return;
              apply(freeze.doc);
              set({ selected: freeze.id });
            }}
            title="Freeze frame (F): insert a 3 s still of the frame at the cursor"
          >
            <Snowflake size={14} />
            Freeze
          </button>
          <button
            disabled={!selectedClip || busy}
            onClick={() =>
              selectedClip &&
              apply(
                state.range
                  ? removeRange(document, selectedClip.id, state.range, false)
                  : remove(pack(document), selectedClip.id, false),
              )
            }
            title="Delete selection or clip, preserving time (Delete)"
          >
            <Trash2 size={14} />
            Delete
          </button>
          <button
            disabled={!selectedClip || busy}
            onClick={() =>
              selectedClip &&
              apply(
                state.range
                  ? removeRange(document, selectedClip.id, state.range, true)
                  : remove(pack(document), selectedClip.id, true),
              )
            }
            title="Ripple delete (Backspace)"
          >
            <ChevronsLeft size={14} />
            Ripple
          </button>
          {(["title", "lower_third"] as Title["style"][]).map((style) => (
            <button
              key={style}
              disabled={busy || !project}
              onClick={() => {
                const added = addTitle(pack(document), style, frame, rate);
                apply(added.doc);
                set({ selected: added.id });
              }}
              title={
                style === "title"
                  ? "Add a title at the cursor, over the picture"
                  : "Add a lower third (name and role) at the cursor"
              }
            >
              {style === "title" ? (
                <Type size={14} />
              ) : (
                <PanelBottom size={14} />
              )}
              {style === "title" ? "Title" : "Lower third"}
            </button>
          ))}
        </div>
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
