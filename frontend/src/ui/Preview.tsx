import {
  useEffect,
  useRef,
  useState,
  type PointerEvent as ReactPointerEvent,
} from "react";
import { Crop, Maximize2, Move, Film, Music2, Minimize2 } from "lucide-react";
import {
  clone,
  fitPicture,
  duration,
  fps,
  layout,
  type Clip,
  type Transform,
} from "../model";
import { useEditor } from "../store";
import { mediaUrl } from "../desktop";

function Media({
  clip,
  frame,
  rate,
  playing,
}: {
  clip: Clip;
  frame: number;
  rate: number;
  playing: boolean;
}) {
  const ref = useRef<HTMLVideoElement & HTMLAudioElement>(null);
  useEffect(() => {
    const media = ref.current;
    if (!media) return;
    const target = (clip.sourceIn + frame - clip.start) / rate;
    const sync = () => {
      if (Math.abs(media.currentTime - target) > (playing ? 0.12 : 0.005))
        media.currentTime = Math.max(0, target);
      if (playing && media.paused)
        void media.play().catch((e) =>
          useEditor.getState().set({
            playing: false,
            error: `Playback could not start: ${String(e)}`,
          }),
        );
      else if (!playing && !media.paused) media.pause();
    };
    media.volume =
      clip.kind === "audio" ? Math.min(1, 10 ** (clip.gainDb / 20)) : 0;
    if (media.readyState) sync();
    else media.addEventListener("loadedmetadata", sync, { once: true });
    return () => media.removeEventListener("loadedmetadata", sync);
  }, [frame, rate, playing, clip]);
  if (clip.kind === "audio")
    return <audio ref={ref} src={mediaUrl(clip.assetId)} preload="auto" />;
  const t = clip.transform;
  return (
    <video
      ref={ref}
      muted
      playsInline
      preload="auto"
      src={mediaUrl(clip.assetId)}
      style={{
        position: "absolute",
        left: t.x,
        top: t.y,
        width: t.width,
        height: t.height,
        objectFit: "fill",
        clipPath: `inset(${t.cropTop * 100}% ${t.cropRight * 100}% ${t.cropBottom * 100}% ${t.cropLeft * 100}%)`,
      }}
    />
  );
}

export function Preview() {
  const { project, document, selected, focus, frame, playing, save, set, busy } =
    useEditor();
  const host = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ width: 800, height: 400 });
  const [mode, setMode] = useState<"scale" | "crop">("scale");
  const [draft, setDraft] = useState<Transform | null>(null);
  const [snap, setSnap] = useState(false);
  useEffect(() => {
    if (!host.current) return;
    const observer = new ResizeObserver(([entry]) =>
      setSize({
        width: entry.contentRect.width,
        height: entry.contentRect.height,
      }),
    );
    observer.observe(host.current);
    return () => observer.disconnect();
  }, []);
  if (!project) return null;
  const { width, height } = project.settings,
    rate = fps(project.settings),
    resolved = layout(document);
  const visible = resolved.clips
    .filter(
      (c) =>
        c.kind !== "gap" && frame >= c.start && frame < c.start + duration(c),
    )
    .toSorted(
      (a, b) =>
        a.layer - b.layer ||
        a.start - b.start ||
        (a.id < b.id ? -1 : a.id > b.id ? 1 : 0),
    );
  const selection = resolved.clips.find(
    (c) => c.id === selected && c.kind === "video" && !!focus,
  );
  const sourceVideo = project.assets.find(a=>a.id===selection?.assetId)?.probe.video;
  const fitted = sourceVideo ? fitPicture(sourceVideo,project.settings) : null;
  const nextFill = !!selection && !!fitted && (Object.keys(fitted) as (keyof Transform)[]).every(k=>Math.abs(fitted[k]-selection.transform[k])<.01);
  const scale = Math.max(
    0.01,
    Math.min((size.width - 90) / width, (size.height - 36) / height),
  );
  const t = draft ?? selection?.transform;
  const bounds = t
    ? {
        x: t.x + t.width * t.cropLeft,
        y: t.y + t.height * t.cropTop,
        w: t.width * (1 - t.cropLeft - t.cropRight),
        h: t.height * (1 - t.cropTop - t.cropBottom),
      }
    : null;

  function gesture(event: ReactPointerEvent, handle: string) {
    if (!selection || !t || busy) return;
    event.stopPropagation();
    event.preventDefault();
    const original = clone(t),
      initialX = event.clientX,
      initialY = event.clientY,
      canvasWidth = width,
      canvasHeight = height;
    let latest = original;
    const onMove = (e: PointerEvent) => {
      let dx = (e.clientX - initialX) / scale,
        dy = (e.clientY - initialY) / scale;
      const next = clone(original);
      let snapped = false;
      if (handle === "move") {
        next.x += dx;
        next.y += dy;
        const left = next.x + next.width * next.cropLeft,
          right = next.x + next.width * (1 - next.cropRight),
          top = next.y + next.height * next.cropTop,
          bottom = next.y + next.height * (1 - next.cropBottom);
        const threshold = 8 / scale;
        for (const [offset, target] of [
          [left, 0],
          [(left + right) / 2, canvasWidth / 2],
          [right, canvasWidth],
        ])
          if (Math.abs(offset - target) < threshold) {
            next.x += target - offset;
            snapped = true;
            break;
          }
        for (const [offset, target] of [
          [top, 0],
          [(top + bottom) / 2, canvasHeight / 2],
          [bottom, canvasHeight],
        ])
          if (Math.abs(offset - target) < threshold) {
            next.y += target - offset;
            snapped = true;
            break;
          }
      } else if (mode === "crop") {
        if (handle.includes("w"))
          next.cropLeft = Math.max(
            0,
            Math.min(
              1 - next.cropRight - 0.02,
              original.cropLeft + dx / original.width,
            ),
          );
        if (handle.includes("e"))
          next.cropRight = Math.max(
            0,
            Math.min(
              1 - next.cropLeft - 0.02,
              original.cropRight - dx / original.width,
            ),
          );
        if (handle.includes("n"))
          next.cropTop = Math.max(
            0,
            Math.min(
              1 - next.cropBottom - 0.02,
              original.cropTop + dy / original.height,
            ),
          );
        if (handle.includes("s"))
          next.cropBottom = Math.max(
            0,
            Math.min(
              1 - next.cropTop - 0.02,
              original.cropBottom - dy / original.height,
            ),
          );
        if (!e.shiftKey) {
          const horizontal = handle.includes("e") || handle.includes("w");
          const ratio =
            (1 - original.cropTop - original.cropBottom) /
            (1 - original.cropLeft - original.cropRight);
          if (horizontal) {
            const change =
              ((1 - next.cropLeft - next.cropRight) * ratio -
                (1 - original.cropTop - original.cropBottom)) /
              2;
            next.cropTop = Math.max(0, original.cropTop - change);
            next.cropBottom = Math.max(0, original.cropBottom - change);
          } else {
            const change =
              ((1 - next.cropTop - next.cropBottom) / ratio -
                (1 - original.cropLeft - original.cropRight)) /
              2;
            next.cropLeft = Math.max(0, original.cropLeft - change);
            next.cropRight = Math.max(0, original.cropRight - change);
          }
        }
        if (e.altKey) {
          if (handle.includes("w")) next.cropRight = next.cropLeft;
          if (handle.includes("e")) next.cropLeft = next.cropRight;
          if (handle.includes("n")) next.cropBottom = next.cropTop;
          if (handle.includes("s")) next.cropTop = next.cropBottom;
        }
        if (
          next.cropLeft + next.cropRight > 0.98 ||
          next.cropTop + next.cropBottom > 0.98
        )
          return;
      } else {
        if (e.altKey) {
          dx *= 2;
          dy *= 2;
        }
        const horizontal = handle.includes("e") || handle.includes("w"),
          vertical = handle.includes("n") || handle.includes("s");
        let w = Math.max(
          32,
          original.width + (handle.includes("w") ? -dx : horizontal ? dx : 0),
        );
        let h = Math.max(
          32,
          original.height + (handle.includes("n") ? -dy : vertical ? dy : 0),
        );
        if (!e.shiftKey) {
          if (horizontal) h = (w * original.height) / original.width;
          else w = (h * original.width) / original.height;
        }
        next.width = w;
        next.height = h;
        if (e.altKey) {
          next.x = original.x + (original.width - w) / 2;
          next.y = original.y + (original.height - h) / 2;
        } else {
          if (handle.includes("w")) next.x = original.x + original.width - w;
          if (handle.includes("n")) next.y = original.y + original.height - h;
        }
      }
      latest = next;
      setDraft(next);
      setSnap(snapped);
    };
    const end = () => {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", end);
      setDraft(null);
      setSnap(false);
      const doc = clone(useEditor.getState().document),
        c = doc.clips.find((c) => c.id === selection.id);
      if (c) {
        c.transform = latest;
        void save(doc);
      }
    };
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", end, { once: true });
  }
  return (
    <section className="preview-panel">
      <div className="panel-title">
        <span>
           Preview & editor
        </span>
        <span className="muted">
          {visible.some((c) => c.kind === "video")
            ? "Composite view"
            : visible.some((c) => c.kind === "audio")
              ? "Audio playback"
              : "Your canvas"}
        </span>
      </div>
      <div className="preview-body" ref={host}>
        <div
          className="viewport"
          data-testid="viewport"
          style={{ width: width * scale, height: height * scale }}
        >
          <div
            className="output-canvas"
            style={{
              width,
              height,
              transform: `scale(${scale})`,
              transformOrigin: "top left",
            }}
          >
            {visible.map((c) => (
              <Media
                key={c.id}
                clip={
                  c.id === selected && draft ? { ...c, transform: draft } : c
                }
                frame={frame}
                rate={rate}
                playing={playing}
              />
            ))}
            {selection && bounds && (
              <div
                className={`selection-bounds ${mode}`}
                style={{
                  left: bounds.x,
                  top: bounds.y,
                  width: bounds.w,
                  height: bounds.h,
                  borderWidth: 1.5 / scale,
                }}
                onPointerDown={(e) => gesture(e, "move")}
              >
                {["nw", "n", "ne", "e", "se", "s", "sw", "w"].map((handle) => (
                  <span
                    key={handle}
                    className={`transform-handle handle-${handle}`}
                    style={{
                      width: 8 / scale,
                      height: 8 / scale,
                      borderWidth: 1 / scale,
                    }}
                    onPointerDown={(e) => gesture(e, handle)}
                  />
                ))}
              </div>
            )}
            {snap && (
              <>
                <div
                  className="snap-x"
                  style={{ left: width / 2, width: 1 / scale }}
                />
                <div
                  className="snap-y"
                  style={{ top: height / 2, height: 1 / scale }}
                />
              </>
            )}
          </div>
          {!visible.some((c) => c.kind === "video") && (
            <div className="preview-empty">
              {visible.some((c) => c.kind === "audio") ? (
                <Music2 size={35} />
              ) : (
                <Film size={35} />
              )}
              <span>
                {visible.length
                  ? "Audio only"
                  : resolved.total
                    ? "Empty frame"
                    : "Every good edit starts with a clip."}
              </span>
              {!resolved.total && <small>Import your footage to begin</small>}
            </div>
          )}
        </div>

      </div>
      <div className="preview-tools">
        {focus && <div className="segmented">
          <button
            title="Scale & move"
            className={mode === "scale" ? "active" : ""}
            onClick={() => setMode("scale")}
          >
            <Maximize2 size={14} />
            Scale
          </button>
          <button
            title="Crop picture"
            className={mode === "crop" ? "active" : ""}
            onClick={() => setMode("crop")}
          >
            <Crop size={14} />
            Crop
          </button>
        </div>}
        {focus && <span className="hint">
          <Move size={12} /> Drag to position · Shift stretch · Alt symmetric
        </span>}
        {selection && (
          <button
            className="button"
            title={nextFill ? "Scale to fill" : "Scale to fit"}
            onClick={() => {
              const doc = clone(document),
                c = doc.clips.find((c) => c.id === selection.id)!,
                asset = project.assets.find((a) => a.id === c.assetId);
              if (asset?.probe.video) {
                c.transform = fitPicture(asset.probe.video,project.settings,nextFill);
                void save(doc);
              }
            }}
          >
            {nextFill ? <Maximize2 size={14}/> : <Minimize2 size={14}/>}
            {nextFill ? "Scale to fill" : "Scale to fit"}
          </button>
        )}
      </div>
    </section>
  );
}
