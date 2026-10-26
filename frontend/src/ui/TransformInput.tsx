import { useEffect, useRef } from "react";
import { updateClip, useEditor } from "../store";
import type { Clip, Transform } from "../model";

export function TransformInput({
  clip,
  field,
}: {
  clip: Clip;
  field: "x" | "y" | "width" | "height";
}) {
  const input = useRef<HTMLInputElement>(null);
  useEffect(() => {
    if (input.current && document.activeElement !== input.current)
      input.current.value = String(Math.round(clip.transform[field]));
  }, [clip.transform[field], clip.id]);
  return (
    <input
      ref={input}
      aria-label={`Clip ${field}`}
      type="number"
      defaultValue={Math.round(clip.transform[field])}
      onChange={(event) => {
        if (!event.currentTarget.value.trim()) return;
        const value = Number(event.currentTarget.value);
        if (
          !Number.isFinite(value) ||
          ((field === "width" || field === "height") && value <= 0)
        )
          return;
        const current = useEditor
          .getState()
          .document.clips.find((c) => c.id === clip.id);
        if (current)
          updateClip(clip.id, {
            transform: {
              ...current.transform,
              [field]: value,
            } satisfies Transform,
          });
      }}
    />
  );
}
