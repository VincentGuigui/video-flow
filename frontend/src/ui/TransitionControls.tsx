import {
  fps,
  layout,
  partners,
  setSpeed,
  span,
  speedOf,
  timecode,
  type Clip,
} from "../model";
import { zoomForRange, type Zoom } from "../zoom";
import { duckRanges, sourceRange, withVolumeRanges } from "../volume";
import { useAnalyses } from "./useAnalysis";
import { currentRange } from "../playback";
import { useEditor } from "../store";
import {
  activeDuration,
  activeTransitions,
  neighbours,
  setFade,
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

// Edge fades of the selected clip (and its linked partner), in seconds.
export function FadeControls({ clip }: { clip: Clip }) {
  const { project, document, save, busy } = useEditor();
  if (!project || clip.kind === "gap") return null;
  const rate = fps(project.settings);
  return (
    <div className="inspector-section transition-controls">
      <span className="overline">FADES</span>
      {(
        [
          ["fadeIn", "Fade in", "From black (or what lies below) at the start"],
          ["fadeOut", "Fade out", "To black (or what lies below) at the end"],
        ] as const
      ).map(([edge, label, hint]) => (
        <label key={edge} className="transition-row" title={hint}>
          <span>{label}</span>
          <span className="transition-duration">
            <input
              aria-label={`${label} duration`}
              type="number"
              min={0}
              step={0.1}
              key={`${clip.id}-${edge}-${clip[edge] ?? 0}`}
              defaultValue={((clip[edge] ?? 0) / rate).toFixed(2)}
              disabled={busy}
              onBlur={(e) => {
                const frames = Math.max(
                  0,
                  Math.round(Number(e.currentTarget.value) * rate),
                );
                if (Number.isFinite(frames) && frames !== (clip[edge] ?? 0))
                  void save(setFade(document, clip.id, edge, frames));
              }}
              onKeyDown={(e) => {
                if (e.key === "Enter") e.currentTarget.blur();
              }}
            />
            s
          </span>
        </label>
      ))}
    </div>
  );
}

const SPEEDS = [0.25, 1 / 3, 0.5, 0.75, 1, 1.25, 1.5, 2, 3, 4];

// Clip speed (and its linked partner); later clips ripple by the change.
export function SpeedControls({ clip }: { clip: Clip }) {
  const { project, document, save, busy } = useEditor();
  if (!project || clip.kind === "gap") return null;
  const current = speedOf(clip),
    range = currentRange(),
    target = range.end - range.start,
    fit = target > 0 ? span(clip) / target : 0;
  const options = SPEEDS.some((s) => Math.abs(s - current) < 0.001)
    ? SPEEDS
    : [...SPEEDS, current].toSorted((a, b) => a - b);
  return (
    <div className="inspector-section transition-controls">
      <span className="overline">SPEED</span>
      <label className="transition-row">
        <span>Playback speed</span>
        <select
          aria-label="Clip speed"
          value={String(options.find((s) => Math.abs(s - current) < 0.001))}
          disabled={busy}
          onChange={(e) =>
            void save(setSpeed(document, clip.id, Number(e.target.value)))
          }
        >
          {options.map((s) => (
            <option key={s} value={String(s)}>
              {Math.round(s * 100)} %
            </option>
          ))}
        </select>
      </label>
      <button
        className="button"
        disabled={
          busy || fit < 0.1 || fit > 10 || Math.abs(fit - current) < 0.001
        }
        title="Change the speed so the clip exactly fills the timeline range"
        onClick={() => void save(setSpeed(document, clip.id, fit))}
      >
        Fit to range ({Math.round(fit * 100)} %)
      </button>
    </div>
  );
}

const ZOOM_SCALES = [1.5, 2, 3, 4];

// Zoom & pan on the selected video clip (spec 21).
export function ZoomControls({ clip }: { clip: Clip }) {
  const { project, document, save, busy } = useEditor();
  if (!project || clip.kind !== "video") return null;
  const rate = fps(project.settings),
    zooms = clip.zooms ?? [],
    placed = layout(document).clips.find((c) => c.id === clip.id),
    candidate = placed ? zoomForRange(placed, currentRange(), rate) : null;
  const update = (next: Zoom[]) =>
    void save({
      ...document,
      clips: document.clips.map((c) =>
        c.id === clip.id ? { ...c, zooms: next } : c,
      ),
    });
  const time = (source: number) =>
    timecode(
      (placed?.start ?? 0) +
        Math.round((source - clip.sourceIn) / speedOf(clip)),
      rate,
    );
  return (
    <div className="inspector-section transition-controls">
      <span className="overline">ZOOM &amp; PAN</span>
      {zooms.map((z, index) => (
        <div key={index} className="zoom-row">
          <span className="zoom-times">
            {time(z.start)} – {time(z.end)}
          </span>
          <select
            aria-label={`Zoom ${index + 1} scale`}
            value={String(z.scale)}
            disabled={busy}
            onChange={(e) =>
              update(
                zooms.map((o, i) =>
                  i === index ? { ...o, scale: Number(e.target.value) } : o,
                ),
              )
            }
          >
            {[...new Set([...ZOOM_SCALES, z.scale])].map((s) => (
              <option key={s} value={String(s)}>
                {Math.round(s * 100)} %
              </option>
            ))}
          </select>
          <div
            className="zoom-focus"
            role="button"
            aria-label={`Zoom ${index + 1} focus point`}
            title="Click where to zoom"
            onClick={(e) => {
              const box = e.currentTarget.getBoundingClientRect();
              const x = Math.min(
                  1,
                  Math.max(0, (e.clientX - box.left) / box.width),
                ),
                y = Math.min(
                  1,
                  Math.max(0, (e.clientY - box.top) / box.height),
                );
              update(zooms.map((o, i) => (i === index ? { ...o, x, y } : o)));
            }}
          >
            <span style={{ left: `${z.x * 100}%`, top: `${z.y * 100}%` }} />
          </div>
          <button
            className="icon-button"
            aria-label={`Remove zoom ${index + 1}`}
            disabled={busy}
            onClick={() => update(zooms.filter((_, i) => i !== index))}
          >
            ×
          </button>
        </div>
      ))}
      <button
        className="button"
        disabled={busy || !candidate}
        title="Zoom 200 % on the part of the clip inside the timeline range (in 0.3 s, out 1 s)"
        onClick={() => candidate && update([...zooms, candidate])}
      >
        Add zoom over range
      </button>
    </div>
  );
}

// Mute ranges and ducking on the audio of the selected clip (spec 21).
export function AudioControls({ clip }: { clip: Clip }) {
  const { project, document, save, busy } = useEditor();
  const others = document.clips.filter(
    (c) => c.enabled && c.kind === "audio" && c.id !== clip.id && c.assetId,
  );
  const analyses = useAnalyses(
    clip.kind === "audio" && !clip.linkId
      ? [...new Set(others.map((c) => c.assetId!))]
      : [],
  );
  if (!project || clip.kind === "gap") return null;
  const rate = fps(project.settings),
    audio = partners(document, clip.id).find((c) => c.kind === "audio");
  if (!audio) return null;
  const ranges = audio.volumeRanges ?? [],
    target = sourceRange(document, audio, currentRange()),
    mutes = ranges.filter((r) => r.kind === "mute"),
    ducks = ranges.filter((r) => r.kind === "duck"),
    ids = new Set([audio.id]);
  const placed = layout(document).clips.find((c) => c.id === audio.id);
  const time = (source: number) =>
    timecode(
      (placed?.start ?? 0) +
        Math.round((source - audio.sourceIn) / speedOf(audio)),
      rate,
    );
  const words = Object.fromEntries(
    Object.entries(analyses).map(([id, a]) => [id, a?.words ?? []]),
  );
  const duck =
    clip.kind === "audio" && !clip.linkId
      ? duckRanges(document, audio.id, words, rate)
      : [];
  return (
    <div className="inspector-section transition-controls">
      <span className="overline">AUDIO</span>
      {mutes.map((r, index) => (
        <div key={index} className="zoom-row">
          <span className="zoom-times">
            Muted {time(r.start)} – {time(r.end)}
          </span>
          <span />
          <span />
          <button
            className="icon-button"
            aria-label={`Remove muted range ${index + 1}`}
            disabled={busy}
            onClick={() =>
              void save(
                withVolumeRanges(document, ids, (c) =>
                  (c.volumeRanges ?? []).filter((x) => x !== r),
                ),
              )
            }
          >
            ×
          </button>
        </div>
      ))}
      <button
        className="button"
        disabled={busy || !target}
        title="Silence the audio inside the timeline range; the picture is kept"
        onClick={() =>
          target &&
          void save(
            withVolumeRanges(document, ids, (c) => [
              ...(c.volumeRanges ?? []),
              {
                ...target,
                gainDb: -60,
                ramp: Math.max(1, Math.round(0.1 * rate * speedOf(c))),
                kind: "mute",
              },
            ]),
          )
        }
      >
        Mute range
      </button>
      {clip.kind === "audio" && !clip.linkId && (
        <>
          <button
            className="button"
            disabled={busy || (!duck.length && !ducks.length)}
            title="Lower this clip by 15 dB wherever other clips have transcribed speech"
            onClick={() =>
              void save(
                withVolumeRanges(document, ids, (c) => [
                  ...(c.volumeRanges ?? []).filter((x) => x.kind !== "duck"),
                  ...duck,
                ]),
              )
            }
          >
            {ducks.length ? "Update ducking" : "Duck under speech"} (
            {duck.length})
          </button>
          {ducks.length > 0 && (
            <button
              className="button"
              disabled={busy}
              onClick={() =>
                void save(
                  withVolumeRanges(document, ids, (c) =>
                    (c.volumeRanges ?? []).filter((x) => x.kind !== "duck"),
                  ),
                )
              }
            >
              Remove ducking ({ducks.length} ranges)
            </button>
          )}
        </>
      )}
    </div>
  );
}
