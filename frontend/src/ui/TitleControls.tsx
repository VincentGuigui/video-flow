import { useEffect, useRef, useState } from "react";
import type { Clip } from "../model";
import { useEditor } from "../store";
import { setTitle, TITLE_PRESETS, type Title } from "../titles";

const SIZES: Record<Title["style"], [string, number][]> = {
  title: [
    ["Small", 0.05],
    ["Medium", 0.08],
    ["Large", 0.11],
    ["Extra large", 0.15],
  ],
  lower_third: [
    ["Small", 0.035],
    ["Medium", 0.05],
    ["Large", 0.065],
    ["Extra large", 0.08],
  ],
};
const OPACITIES = [0.5, 0.75, 0.85, 1];

// Text, style and colours of the selected text clip (spec 21).
export function TitleControls({ clip }: { clip: Clip }) {
  const { save, busy } = useEditor();
  const title = clip.title;
  const [text, setText] = useState(title?.text ?? "");
  const timer = useRef<ReturnType<typeof setTimeout>>(undefined);
  useEffect(() => setText(title?.text ?? ""), [clip.id, title?.text]);
  useEffect(() => () => clearTimeout(timer.current), []);
  if (!title) return null;
  const update = (change: Partial<Title>) =>
    void save(setTitle(useEditor.getState().document, clip.id, change));
  // Colour pickers report every move: save once the choice settles.
  const later = (change: Partial<Title>) => {
    clearTimeout(timer.current);
    timer.current = setTimeout(() => update(change), 400);
  };
  const commitText = () => {
    if (text.trim() && text !== title.text) update({ text });
    else setText(title.text);
  };
  const sizes = SIZES[title.style].some(([, s]) => s === title.size)
    ? SIZES[title.style]
    : [...SIZES[title.style], ["Custom", title.size] as [string, number]];
  return (
    <div className="inspector-section transition-controls title-controls">
      <span className="overline">TEXT</span>
      <textarea
        aria-label="Title text"
        rows={3}
        value={text}
        onChange={(e) => setText(e.target.value)}
        onBlur={commitText}
        onKeyDown={(e) => {
          if (e.key === "Enter" && (e.ctrlKey || e.metaKey))
            e.currentTarget.blur();
          e.stopPropagation(); // typing must not trigger editor shortcuts
        }}
      />
      <label className="transition-row">
        <span>Style</span>
        <select
          aria-label="Title style"
          value={title.style}
          disabled={busy}
          onChange={(e) => {
            const style = e.target.value as Title["style"],
              preset = TITLE_PRESETS[style].title;
            update({
              style,
              size: preset.size,
              box: preset.box,
              boxColor: preset.boxColor,
              boxOpacity: preset.boxOpacity,
            });
          }}
        >
          <option value="title">Title (centred)</option>
          <option value="lower_third">Lower third</option>
        </select>
      </label>
      <label className="transition-row">
        <span>Size</span>
        <select
          aria-label="Title size"
          value={String(title.size)}
          disabled={busy}
          onChange={(e) => update({ size: Number(e.target.value) })}
        >
          {sizes.map(([label, size]) => (
            <option key={label} value={String(size)}>
              {label}
            </option>
          ))}
        </select>
      </label>
      <label className="transition-row">
        <span>Text colour</span>
        <input
          aria-label="Title colour"
          type="color"
          defaultValue={title.color}
          key={`${clip.id}-${title.color}`}
          disabled={busy}
          onChange={(e) => later({ color: e.target.value })}
        />
      </label>
      <label className="transition-row">
        <span>Box behind text</span>
        <input
          aria-label="Title box"
          type="checkbox"
          checked={title.box}
          disabled={busy}
          onChange={(e) => update({ box: e.target.checked })}
        />
      </label>
      {title.box && (
        <>
          <label className="transition-row">
            <span>Box colour</span>
            <input
              aria-label="Box colour"
              type="color"
              defaultValue={title.boxColor}
              key={`${clip.id}-${title.boxColor}`}
              disabled={busy}
              onChange={(e) => later({ boxColor: e.target.value })}
            />
          </label>
          <label className="transition-row">
            <span>Box opacity</span>
            <select
              aria-label="Box opacity"
              value={String(title.boxOpacity)}
              disabled={busy}
              onChange={(e) => update({ boxOpacity: Number(e.target.value) })}
            >
              {(OPACITIES.includes(title.boxOpacity)
                ? OPACITIES
                : [...OPACITIES, title.boxOpacity].toSorted()
              ).map((o) => (
                <option key={o} value={String(o)}>
                  {Math.round(o * 100)} %
                </option>
              ))}
            </select>
          </label>
        </>
      )}
    </div>
  );
}
