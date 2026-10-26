import { fps, type Clip } from "../model";
import { useEditor } from "../store";
import {
  activeDuration,
  activeTransitions,
  neighbours,
  setAllTransitions,
  setTransition,
  sourceFramesFor,
  transitionAt,
  TRANSITION_LABELS,
  type TransitionType,
} from "../transitions";

// Transitions on the cuts before and after the selected video clip.
export function TransitionControls({ clip }: { clip: Clip }) {
  const { project, document, save, busy } = useEditor();
  if (!project || clip.kind !== "video") return null;
  const rate = fps(project.settings);
  const fallback = project.settings.defaultTransition as
    { durationUs?: number } | undefined;
  const defaultFrames = Math.max(
    1,
    Math.round(((fallback?.durationUs ?? 500_000) * rate) / 1_000_000),
  );
  const { previous, next } = neighbours(document, clip.id);
  const active = activeTransitions(document, sourceFramesFor(project));
  const cuts = [
    previous && {
      label: `In · from ${previous.name}`,
      left: previous,
      right: clip,
    },
    next && { label: `Out · to ${next.name}`, left: clip, right: next },
  ].filter((c) => !!c);
  if (!cuts.length) return null;
  const chosen = cuts
    .map((c) => transitionAt(document, c.left.id, c.right.id))
    .find((t) => !!t);
  return (
    <div className="inspector-section transition-controls">
      <span className="overline">TRANSITIONS</span>
      {cuts.map(({ label, left, right }) => {
        const t = transitionAt(document, left.id, right.id);
        const a = active.find((x) => x.transition === t);
        const frames = t?.duration ?? defaultFrames;
        return (
          <div key={label} className="transition-row">
            <span className="transition-label" title={label}>
              {label}
            </span>
            <select
              aria-label={`${label} transition`}
              value={t?.type ?? "cut"}
              disabled={busy}
              onChange={(e) => {
                const type =
                  e.target.value === "cut"
                    ? null
                    : (e.target.value as TransitionType);
                void save(
                  setTransition(document, left.id, right.id, type, frames),
                );
              }}
            >
              <option value="cut">Cut</option>
              {Object.entries(TRANSITION_LABELS).map(([value, name]) => (
                <option key={value} value={value}>
                  {name}
                </option>
              ))}
            </select>
            {t && (
              <label className="transition-duration">
                <input
                  aria-label={`${label} duration`}
                  type="number"
                  min={1 / rate}
                  step={0.1}
                  defaultValue={(t.duration / rate).toFixed(2)}
                  key={`${t.id}-${t.duration}`}
                  disabled={busy}
                  onBlur={(e) => {
                    const seconds = Number(e.currentTarget.value);
                    if (
                      seconds > 0 &&
                      Math.round(seconds * rate) !== t.duration
                    )
                      void save(
                        setTransition(
                          document,
                          left.id,
                          right.id,
                          t.type,
                          seconds * rate,
                        ),
                      );
                  }}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") e.currentTarget.blur();
                  }}
                />
                s
              </label>
            )}
            {t && a && activeDuration(a) < t.duration && (
              <small className="transition-warning">
                Shortened to {(activeDuration(a) / rate).toFixed(2)} s: not
                enough source media or clip length.
              </small>
            )}
          </div>
        );
      })}
      <button
        className="button"
        disabled={busy}
        title="Use this transition on every cut between adjacent video clips"
        onClick={() =>
          void save(
            setAllTransitions(
              document,
              chosen?.type ?? "dissolve",
              chosen?.duration ?? defaultFrames,
            ),
          )
        }
      >
        Apply{" "}
        {chosen
          ? TRANSITION_LABELS[chosen.type].toLowerCase()
          : "cross dissolve"}{" "}
        to all cuts
      </button>
    </div>
  );
}
