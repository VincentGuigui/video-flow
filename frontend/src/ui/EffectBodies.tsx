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
import { duckRanges, sourceRange, withVolumeRanges } from "../volume";
import { useAnalyses } from "./useAnalysis";
import { currentRange } from "../playback";
import { useEditor } from "../store";
import { setFade } from "../transitions";

// Settings of each clip effect, shown inside its card in the Effects tab
// (docs/features/finishing/clip-effects.md).

// Edge fade of the selected clip (and its linked partner), in seconds.
export function FadeBody({
  clip,
  edge,
}: {
  clip: Clip;
  edge: "fadeIn" | "fadeOut";
}) {
  const { project, document, save, busy } = useEditor();
  if (!project) return null;
  const rate = fps(project.settings);
  const label = edge === "fadeIn" ? "Fade in" : "Fade out";
  return (
    <div className="effect-body">
      <label className="transition-row">
        <span>Duration</span>
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
    </div>
  );
}

const SPEEDS = [0.25, 1 / 3, 0.5, 0.75, 1, 1.25, 1.5, 2, 3, 4];

// Clip speed (and its linked partner); later clips ripple by the change.
export function SpeedBody({ clip }: { clip: Clip }) {
  const { project, document, save, busy } = useEditor();
  if (!project || clip.kind === "gap" || clip.kind === "text") return null;
  const current = speedOf(clip),
    range = currentRange(),
    target = range.end - range.start,
    fit = target > 0 ? span(clip) / target : 0;
  const options = SPEEDS.some((s) => Math.abs(s - current) < 0.001)
    ? SPEEDS
    : [...SPEEDS, current].toSorted((a, b) => a - b);
  return (
    <div className="effect-body">
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

function useAudioPartner(clip: Clip) {
  const { project, document } = useEditor();
  const audio = partners(document, clip.id).find((c) => c.kind === "audio");
  const rate = project ? fps(project.settings) : 30;
  const placed = audio && layout(document).clips.find((c) => c.id === audio.id);
  const time = (source: number) =>
    audio
      ? timecode(
          (placed?.start ?? 0) +
            Math.round((source - audio.sourceIn) / speedOf(audio)),
          rate,
        )
      : "";
  return { audio, rate, time };
}

// Mute ranges on the audio of the selected clip.
export function MuteBody({ clip }: { clip: Clip }) {
  const { document, save, busy } = useEditor();
  const { audio, rate, time } = useAudioPartner(clip);
  if (!audio) return null;
  const ids = new Set([audio.id]),
    mutes = (audio.volumeRanges ?? []).filter((r) => r.kind === "mute"),
    target = sourceRange(document, audio, currentRange());
  return (
    <div className="effect-body">
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
        Mute timeline range
      </button>
    </div>
  );
}

// Ducking of a music clip (audio not linked to a video) under transcribed speech.
export function DuckBody({ clip }: { clip: Clip }) {
  const { document, save, busy } = useEditor();
  const others = document.clips.filter(
    (c) => c.enabled && c.kind === "audio" && c.id !== clip.id && c.assetId,
  );
  const analyses = useAnalyses([...new Set(others.map((c) => c.assetId!))]);
  const { audio, rate } = useAudioPartner(clip);
  if (!audio) return null;
  const ids = new Set([audio.id]),
    ducks = (audio.volumeRanges ?? []).filter((r) => r.kind === "duck");
  const words = Object.fromEntries(
    Object.entries(analyses).map(([id, a]) => [id, a?.words ?? []]),
  );
  const duck = duckRanges(document, audio.id, words, rate);
  return (
    <div className="effect-body">
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
        {ducks.length ? "Update ducking" : "Duck under speech"} ({duck.length})
      </button>
    </div>
  );
}
