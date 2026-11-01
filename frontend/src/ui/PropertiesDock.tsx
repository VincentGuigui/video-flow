import { useEffect, useRef, useState, type ReactNode } from "react";
import {
  ChevronsDownUp,
  ChevronsUpDown,
  Pin,
  PinOff,
  SlidersHorizontal,
} from "lucide-react";
import { clampWidth, type PanelLayout } from "../panel";

const COLLAPSE_DELAY = 300;

// Frame of the properties panel. Pinned, it takes its width from the editor area: in
// "half" height beside the preview only, in "tall" height beside the preview, timeline
// and flow. Unpinned, it floats over the other blocks without changing their width, and
// folds into a narrow strip when the pointer leaves it; the pointer on the strip opens
// it again. Its left edge resizes it.
export function PropertiesDock({
  layout,
  onChange,
  children,
}: {
  layout: PanelLayout;
  onChange: (layout: PanelLayout) => void;
  children: (controls: ReactNode) => ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const [resizing, setResizing] = useState(false);
  const dock = useRef<HTMLElement>(null);
  const timer = useRef<number | undefined>(undefined);
  const drag = useRef<{ x: number; width: number } | null>(null);
  const floating = !layout.pinned;
  const shown = !floating || open || resizing;
  useEffect(() => () => window.clearTimeout(timer.current), []);
  useEffect(() => {
    if (layout.pinned) setOpen(false);
  }, [layout.pinned]);

  function enter() {
    window.clearTimeout(timer.current);
    if (floating) setOpen(true);
  }
  function leave(event: React.MouseEvent) {
    if (!floating || resizing || event.buttons) return;
    // A native <select> list sits outside the page: leaving for it keeps the panel open.
    const active = window.document.activeElement;
    if (active?.tagName === "SELECT" && dock.current?.contains(active)) return;
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => setOpen(false), COLLAPSE_DELAY);
  }
  function available() {
    return (
      dock.current?.closest(".workspace")?.clientWidth ?? window.innerWidth
    );
  }

  const controls = (
    <div className="dock-controls">
      <button
        className="icon-button"
        aria-label={layout.height === "half" ? "Tall panel" : "Half panel"}
        title={
          layout.height === "half"
            ? "Tall: beside the preview, timeline and flow"
            : "Half: beside the preview only"
        }
        onClick={() =>
          onChange({
            ...layout,
            height: layout.height === "half" ? "tall" : "half",
          })
        }
      >
        {layout.height === "half" ? (
          <ChevronsUpDown size={14} />
        ) : (
          <ChevronsDownUp size={14} />
        )}
      </button>
      <button
        className="icon-button"
        aria-label={layout.pinned ? "Unpin panel" : "Pin panel"}
        title={
          layout.pinned
            ? "Unpin: float over the editor and fold away when the pointer leaves"
            : "Pin: keep the panel open beside the editor"
        }
        onClick={() => onChange({ ...layout, pinned: !layout.pinned })}
      >
        {layout.pinned ? <PinOff size={14} /> : <Pin size={14} />}
      </button>
    </div>
  );

  return (
    <aside
      ref={dock}
      className={`properties-dock ${layout.height} ${floating ? "floating" : "pinned"} ${shown ? "open" : "folded"}`}
      style={shown ? { width: layout.width } : undefined}
      onMouseEnter={enter}
      onMouseLeave={leave}
    >
      {shown ? (
        <>
          <div
            className="dock-resize"
            role="separator"
            aria-orientation="vertical"
            aria-label="Resize properties panel"
            title="Drag to resize"
            onPointerDown={(e) => {
              e.preventDefault();
              e.currentTarget.setPointerCapture(e.pointerId);
              drag.current = { x: e.clientX, width: layout.width };
              setResizing(true);
            }}
            onPointerMove={(e) => {
              if (!drag.current) return;
              onChange({
                ...layout,
                width: clampWidth(
                  drag.current.width + drag.current.x - e.clientX,
                  available(),
                ),
              });
            }}
            onPointerUp={() => {
              drag.current = null;
              setResizing(false);
            }}
            onPointerCancel={() => {
              drag.current = null;
              setResizing(false);
            }}
          />
          {children(controls)}
        </>
      ) : (
        <button
          className="dock-strip"
          aria-label="Open properties"
          onClick={() => setOpen(true)}
          onFocus={() => setOpen(true)}
        >
          <SlidersHorizontal size={15} />
          <span>Properties</span>
        </button>
      )}
    </aside>
  );
}
