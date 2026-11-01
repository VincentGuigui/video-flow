import { useEffect, useRef } from "react";
import { ChevronLeft, ChevronRight, Diamond, Trash2, X } from "lucide-react";
import {
  duration,
  fps,
  layout,
  timecode,
  type Clip,
  type Transform,
} from "../model";
import { useEditor } from "../store";
import {
  addKeyframe,
  clearKeyframes,
  keyframeOffsets,
  removeKeyframe,
  setEase,
  setTransformAt,
  sourceAt,
  transformAtFrame,
} from "../keyframes";

type Field = {
  label: string;
  unit: string;
  get: (t: Transform) => number;
  set: (t: Transform, value: number) => Transform | null;
};

const percent = (key: "cropLeft" | "cropRight" | "cropTop" | "cropBottom") =>
  ({
    label: key.replace("crop", "Crop "),
    unit: "%",
    get: (t) => t[key] * 100,
    set: (t, v) => {
      const next = { ...t, [key]: Math.max(0, v / 100) };
      return next.cropLeft + next.cropRight < 1 &&
        next.cropTop + next.cropBottom < 1
        ? next
        : null;
    },
  }) satisfies Field;

const FIELDS: Field[] = [
  { label: "X", unit: "px", get: (t) => t.x, set: (t, v) => ({ ...t, x: v }) },
  { label: "Y", unit: "px", get: (t) => t.y, set: (t, v) => ({ ...t, y: v }) },
  {
    label: "Width",
    unit: "px",
    get: (t) => t.width,
    set: (t, v) => (v > 0 ? { ...t, width: v } : null),
  },
  {
    label: "Height",
    unit: "px",
    get: (t) => t.height,
    set: (t, v) => (v > 0 ? { ...t, height: v } : null),
  },
  {
    label: "Rotation",
    unit: "°",
    get: (t) => t.rotation ?? 0,
    set: (t, v) => (Math.abs(v) <= 3600 ? { ...t, rotation: v } : null),
  },
  {
    label: "Opacity",
    unit: "%",
    get: (t) => (t.opacity ?? 1) * 100,
    set: (t, v) => ({ ...t, opacity: Math.min(1, Math.max(0, v / 100)) }),
  },
  percent("cropLeft"),
  percent("cropRight"),
  percent("cropTop"),
  percent("cropBottom"),
];

// Animation tab: keyframes of a video clip and its transform at the cursor
// (docs/features/keyframes.md).
export function AnimationTab({ clip }: { clip: Clip }) {
  const { project, document, frame, save, busy, set } = useEditor();
  const chosen = useEditor((s) => s.keyframe);
  if (!project) return null;
  const rate = fps(project.settings);
  const placed = layout(document).clips.find((c) => c.id === clip.id);
  if (!placed) return null;
  const inside =
    frame >= placed.start && frame < placed.start + duration(placed);
  const at = inside
    ? frame
    : Math.min(
        Math.max(frame, placed.start),
        placed.start + duration(placed) - 1,
      );
  const current = transformAtFrame(placed, at);
  const keys = keyframeOffsets(placed);
  const here = keys.find((k) => k.frame === sourceAt(placed, at));
  const reference = clip.transform;
  // Uniform scale about the centre, relative to the clip's base size.
  const scale: Field = {
    label: "Scale",
    unit: "%",
    get: (t) => (t.width / reference.width) * 100,
    set: (t, v) => {
      if (v <= 0) return null;
      const width = (reference.width * v) / 100,
        height = (t.height / t.width) * width;
      return {
        ...t,
        x: t.x + (t.width - width) / 2,
        y: t.y + (t.height - height) / 2,
        width,
        height,
      };
    },
  };
  const fields = [...FIELDS.slice(0, 2), scale, ...FIELDS.slice(2)];
  const go = (offset: number) =>
    set({ frame: placed.start + offset, playing: false });
  const previous = keys.toReversed().find((k) => placed.start + k.offset < at);
  const next = keys.find((k) => placed.start + k.offset > at);
  return (
    <div className="inspector-content animation-tab">
      <div className="effects-heading">
        <span className="overline">KEYFRAMES</span>
        <div className="keyframe-nav">
          <button
            className="icon-button"
            aria-label="Previous keyframe"
            disabled={!previous}
            onClick={() => previous && go(previous.offset)}
          >
            <ChevronLeft size={15} />
          </button>
          <button
            className="button"
            disabled={busy || !inside || !!here}
            title="Add a keyframe at the cursor holding the transform shown there (K)"
            onClick={() =>
              void save(addKeyframe(document, clip.id, frame, placed))
            }
          >
            <Diamond size={13} />
            Add at cursor
          </button>
          <button
            className="icon-button"
            aria-label="Next keyframe"
            disabled={!next}
            onClick={() => next && go(next.offset)}
          >
            <ChevronRight size={15} />
          </button>
        </div>
      </div>
      {!keys.length && (
        <p className="muted effects-empty">
          No keyframe: the values below apply to the whole clip. Add a keyframe,
          move the cursor, add another and change its values: the transform is
          interpolated between them.
        </p>
      )}
      <div className="keyframe-list">
        {keys.map((k) => {
          const key = clip.keyframes?.find((x) => x.frame === k.frame);
          return (
            <div
              key={k.frame}
              className={`keyframe-row ${here?.frame === k.frame ? "current" : ""} ${chosen === k.frame ? "selected" : ""}`}
            >
              <button
                className="keyframe-time"
                title="Go to this keyframe"
                onClick={() => {
                  go(k.offset);
                  set({ keyframe: k.frame });
                }}
              >
                <Diamond size={11} />
                {timecode(placed.start + k.offset, rate)}
              </button>
              <select
                aria-label="Easing after this keyframe"
                value={key?.ease ?? "smooth"}
                disabled={busy}
                onChange={(e) =>
                  void save(
                    setEase(
                      document,
                      clip.id,
                      k.frame,
                      e.target.value as "linear" | "smooth",
                    ),
                  )
                }
              >
                <option value="smooth">Smooth</option>
                <option value="linear">Linear</option>
              </select>
              <button
                className="icon-button"
                aria-label="Remove keyframe"
                disabled={busy}
                onClick={() =>
                  void save(removeKeyframe(document, clip.id, k.frame))
                }
              >
                <X size={14} />
              </button>
            </div>
          );
        })}
      </div>
      <span className="overline">
        {keys.length
          ? here
            ? "AT THIS KEYFRAME"
            : "AT THE CURSOR"
          : "TRANSFORM"}
      </span>
      {keys.length > 0 && !here && (
        <p className="muted effects-empty">
          Changing a value adds a keyframe at the cursor.
        </p>
      )}
      <div className="transform-grid animation-fields">
        {fields.map((f) => (
          <label key={f.label}>
            {f.label}
            <NumberField
              value={f.get(current)}
              unit={f.unit}
              disabled={busy || (keys.length > 0 && !inside)}
              onCommit={(value) => {
                const changed = f.set(current, value);
                if (changed)
                  void save(
                    setTransformAt(document, clip.id, at, changed, placed),
                  );
              }}
            />
          </label>
        ))}
      </div>
      {keys.length > 0 && (
        <button
          className="button"
          disabled={busy}
          title="Delete every keyframe; the clip keeps the transform shown at the cursor"
          onClick={() =>
            void save(clearKeyframes(document, clip.id, at, placed))
          }
        >
          <Trash2 size={14} />
          Remove animation
        </button>
      )}
    </div>
  );
}

// A number committed on blur or Enter, rounded for display.
function NumberField({
  value,
  unit,
  disabled,
  onCommit,
}: {
  value: number;
  unit: string;
  disabled: boolean;
  onCommit: (value: number) => void;
}) {
  const input = useRef<HTMLInputElement>(null);
  const shown = String(Math.round(value * 10) / 10);
  useEffect(() => {
    if (input.current && window.document.activeElement !== input.current)
      input.current.value = shown;
  }, [shown]);
  return (
    <span className="number-field">
      <input
        ref={input}
        type="number"
        step="any"
        defaultValue={shown}
        disabled={disabled}
        onBlur={(e) => {
          const next = Number(e.currentTarget.value);
          if (
            e.currentTarget.value.trim() &&
            Number.isFinite(next) &&
            String(next) !== shown
          )
            onCommit(next);
          else e.currentTarget.value = shown;
        }}
        onKeyDown={(e) => {
          if (e.key === "Enter") e.currentTarget.blur();
        }}
      />
      <small>{unit}</small>
    </span>
  );
}
