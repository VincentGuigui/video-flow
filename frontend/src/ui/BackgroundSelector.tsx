import { updateClip } from "../store";
import type { Clip } from "../model";

export function BackgroundSelector({
  clip,
  disabled,
}: {
  clip: Clip;
  disabled: boolean;
}) {
  const background = clip.background ?? {
    mode: "transparent",
    color: "#000000",
  };
  return (
    <div className="background-selector">
      <label>
        Background
        <select
          aria-label="Clip background"
          disabled={disabled}
          value={background.mode}
          onChange={(e) =>
            updateClip(clip.id, {
              background: { ...background, mode: e.target.value },
            })
          }
        >
          <option value="color">Color</option>
          <option value="transparent">Transparent</option>
          <option value="blur">Blurred video</option>
        </select>
      </label>
      {background.mode === "color" && (
        <input
          aria-label="Background color"
          title="Background color"
          type="color"
          disabled={disabled}
          value={background.color}
          onChange={(e) =>
            updateClip(clip.id, {
              background: { ...background, color: e.target.value },
            })
          }
        />
      )}
    </div>
  );
}
