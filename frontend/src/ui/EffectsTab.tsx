import { useEffect, useRef, useState, type ReactNode } from "react";
import { ChevronDown, Plus, X } from "lucide-react";
import { fps, type Clip } from "../model";
import { useEditor } from "../store";
import {
  activeDuration,
  activeTransitions,
  cutKey,
  neighbours,
  setAllTransitions,
  setTransition,
  sourceFramesFor,
  transitionAt,
  TRANSITION_LABELS,
  type TransitionType,
} from "../transitions";
import { EFFECTS, type EffectDef, type EffectId } from "../effects";
import {
  DuckBody,
  FadeBody,
  MuteBody,
  SpeedBody,
  ZoomBody,
} from "./EffectBodies";

const TYPES: (TransitionType | "cut")[] = [
  "cut",
  "dissolve",
  "dip_black",
  "dip_white",
];
const label = (type: TransitionType | "cut") =>
  type === "cut" ? "Cut" : TRANSITION_LABELS[type];
const SHORT: Record<TransitionType | "cut", string> = {
  cut: "Cut",
  dissolve: "Dissolve",
  dip_black: "Dip black",
  dip_white: "Dip white",
};

const BODIES: Record<EffectId, (props: { clip: Clip }) => ReactNode> = {
  fadeIn: ({ clip }) => <FadeBody clip={clip} edge="fadeIn" />,
  fadeOut: ({ clip }) => <FadeBody clip={clip} edge="fadeOut" />,
  speed: SpeedBody,
  zoom: ZoomBody,
  mute: MuteBody,
  duck: DuckBody,
};

// Effects tab of the properties panel: the transitions on the cuts before and after the
// selected video clip, then one card per clip effect in use. "Add effect" lists the
// effects that apply to the clip and are not in use yet (src/effects.ts).
export function EffectsTab({ clip }: { clip: Clip }) {
  const { project, document } = useEditor();
  const [opened, setOpened] = useState<EffectId[]>([]);
  useEffect(() => setOpened([]), [clip.id]);
  if (!project) return null;
  const applicable = EFFECTS.filter((e) => e.applies(document, clip));
  const shown = applicable.filter(
    (e) => e.active(document, clip) || opened.includes(e.id),
  );
  const available = applicable.filter((e) => !shown.includes(e));
  return (
    <div className="inspector-content effects-tab">
      <Transitions clip={clip} />
      <div className="effects-heading">
        <span className="overline">EFFECTS</span>
        <AddEffect
          clip={clip}
          available={available}
          onOpen={(id) => setOpened((o) => [...o, id])}
        />
      </div>
      {shown.map((effect) => (
        <EffectCard
          key={effect.id}
          clip={clip}
          effect={effect}
          onClose={() => setOpened((o) => o.filter((id) => id !== effect.id))}
        />
      ))}
      {!shown.length && (
        <p className="muted effects-empty">
          No effect on this clip.{" "}
          {available.length > 0 && "Add one with the button above."}
        </p>
      )}
    </div>
  );
}

function AddEffect({
  clip,
  available,
  onOpen,
}: {
  clip: Clip;
  available: EffectDef[];
  onOpen: (id: EffectId) => void;
}) {
  const { project, document, save, busy } = useEditor();
  const [menu, setMenu] = useState(false);
  const rate = project ? fps(project.settings) : 30;
  return (
    <div className="add-effect">
      <button
        className="button"
        disabled={busy || !available.length}
        aria-expanded={menu}
        onClick={() => setMenu(!menu)}
      >
        <Plus size={14} />
        Add effect
      </button>
      {menu && (
        <div className="add-effect-menu" role="menu">
          {available.map((effect) => (
            <button
              key={effect.id}
              role="menuitem"
              onClick={() => {
                setMenu(false);
                onOpen(effect.id);
                const next = effect.add(document, clip, rate);
                if (next) void save(next);
              }}
            >
              <strong>{effect.label}</strong>
              <small>{effect.description}</small>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function EffectCard({
  clip,
  effect,
  onClose,
}: {
  clip: Clip;
  effect: EffectDef;
  onClose: () => void;
}) {
  const { project, document, save, busy } = useEditor();
  const [folded, setFolded] = useState(false);
  const rate = project ? fps(project.settings) : 30;
  const Body = BODIES[effect.id];
  const active = effect.active(document, clip);
  return (
    <section className={`effect-card ${folded ? "folded" : ""}`}>
      <header>
        <button
          className="effect-title"
          aria-expanded={!folded}
          title={effect.description}
          onClick={() => setFolded(!folded)}
        >
          <ChevronDown size={14} />
          <strong>{effect.label}</strong>
          {active && <small>{effect.summary(document, clip, rate)}</small>}
        </button>
        <button
          className="icon-button"
          aria-label={`Remove ${effect.label}`}
          title="Remove this effect"
          disabled={busy}
          onClick={() => {
            onClose();
            if (active) void save(effect.remove(document, clip));
          }}
        >
          <X size={14} />
        </button>
      </header>
      {!folded && <Body clip={clip} />}
    </section>
  );
}

// Transition cards for the cut before (in) and after (out) the clip.
function Transitions({ clip }: { clip: Clip }) {
  const { project, document, save, busy } = useEditor();
  if (!project || clip.kind !== "video") return null;
  const rate = fps(project.settings);
  // Default duration of a new transition (project setting, 0.5 s otherwise).
  const fallback = project.settings.defaultTransition as
    { durationUs?: number } | undefined;
  const defaultFrames = Math.max(
    1,
    Math.round(((fallback?.durationUs ?? 500_000) * rate) / 1_000_000),
  );
  const { previous, next } = neighbours(document, clip.id);
  const cuts = [
    previous && {
      side: "In",
      other: previous.name,
      left: previous,
      right: clip,
    },
    next && { side: "Out", other: next.name, left: clip, right: next },
  ].filter((c) => !!c);
  const chosen = cuts
    .map((c) => transitionAt(document, c.left.id, c.right.id))
    .find((t) => !!t);
  return (
    <>
      <span className="overline">TRANSITIONS</span>
      {!cuts.length && (
        <p className="muted effects-empty">
          No adjacent video clip on this lane: place one right before or after
          to add a transition.
        </p>
      )}
      {cuts.map((c) => (
        <TransitionCard
          key={c.side}
          title={`${c.side} · ${c.side === "In" ? "from" : "to"} ${c.other}`}
          leftId={c.left.id}
          rightId={c.right.id}
          defaultFrames={defaultFrames}
        />
      ))}
      {cuts.length > 0 && (
        <button
          className="button apply-all"
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
      )}
    </>
  );
}

function TransitionCard({
  title,
  leftId,
  rightId,
  defaultFrames,
}: {
  title: string;
  leftId: string;
  rightId: string;
  defaultFrames: number;
}) {
  const { project, document, save, busy } = useEditor();
  const focus = useEditor((s) => s.effectFocus);
  const card = useRef<HTMLElement>(null);
  const key = cutKey(leftId, rightId);
  const focused = focus === key;
  useEffect(() => {
    if (focused) card.current?.scrollIntoView({ block: "nearest" });
  }, [focused]);
  if (!project) return null;
  const rate = fps(project.settings);
  const t = transitionAt(document, leftId, rightId);
  const a = activeTransitions(document, sourceFramesFor(project)).find(
    (x) => x.transition === t,
  );
  const frames = t?.duration ?? defaultFrames;
  return (
    <section
      ref={card}
      className={`effect-card transition-card ${focused ? "focused" : ""}`}
      data-cut={key}
    >
      <header>
        <strong className="effect-title-static" title={title}>
          {title}
        </strong>
      </header>
      <div
        className="transition-types"
        role="radiogroup"
        aria-label={`${title} transition`}
      >
        {TYPES.map((type) => (
          <button
            key={type}
            role="radio"
            aria-checked={(t?.type ?? "cut") === type}
            className={`transition-type ${(t?.type ?? "cut") === type ? "active" : ""}`}
            disabled={busy}
            title={label(type)}
            onClick={() =>
              void save(
                setTransition(
                  document,
                  leftId,
                  rightId,
                  type === "cut" ? null : type,
                  frames,
                ),
              )
            }
          >
            <span className={`transition-swatch ${type}`} />
            <small>{SHORT[type]}</small>
          </button>
        ))}
      </div>
      {t && (
        <label className="transition-row">
          <span>Duration</span>
          <span className="transition-duration">
            <input
              aria-label={`${title} duration`}
              type="number"
              min={1 / rate}
              step={0.1}
              defaultValue={(t.duration / rate).toFixed(2)}
              key={`${t.id}-${t.duration}`}
              disabled={busy}
              onBlur={(e) => {
                const seconds = Number(e.currentTarget.value);
                if (seconds > 0 && Math.round(seconds * rate) !== t.duration)
                  void save(
                    setTransition(
                      document,
                      leftId,
                      rightId,
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
          </span>
        </label>
      )}
      {t && a && activeDuration(a) < t.duration && (
        <small className="transition-warning">
          Shortened to {(activeDuration(a) / rate).toFixed(2)} s: not enough
          source media or clip length.
        </small>
      )}
    </section>
  );
}
