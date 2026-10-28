// Mirror of backend/videoflow/editor/transitions.py: keep both in step.
import {
  duration,
  layout,
  partners,
  toSource,
  toTimeline,
  uid,
  type Clip,
  type Document,
  type Project,
} from "./model";

export type TransitionType = "dissolve" | "dip_black" | "dip_white";
export interface Transition {
  id: string;
  leftId: string;
  rightId: string;
  type: TransitionType;
  duration: number; // requested frames, centred on the cut
}
export const TRANSITION_LABELS: Record<TransitionType, string> = {
  dissolve: "Cross dissolve",
  dip_black: "Dip to black",
  dip_white: "Dip to white",
};
export interface Active {
  transition: Transition;
  cut: number;
  before: number;
  after: number;
}
export const activeDuration = (a: Active) => a.before + a.after;

// Frames available in each clip's source, for dissolve handles.
export type SourceFrames = (clip: Clip) => number;
export function sourceFramesFor(project: Project | null): SourceFrames {
  const rate = project
    ? project.settings.frameRate.num / project.settings.frameRate.den
    : 30;
  return (clip) => {
    const asset = project?.assets.find((a) => a.id === clip.assetId);
    return asset
      ? Math.round((asset.probe.durationUs * rate) / 1_000_000)
      : clip.sourceOut;
  };
}

function adjacent(left: Clip | undefined, right: Clip | undefined) {
  return (
    !!left &&
    !!right &&
    left.kind === "video" &&
    right.kind === "video" &&
    left.layer === right.layer &&
    left.start + duration(left) === right.start
  );
}

export function activeTransitions(
  doc: Document,
  sourceFrames: SourceFrames,
): Active[] {
  const clips = layout(doc).clips,
    byId = new Map(clips.map((c) => [c.id, c])),
    seen = new Set<string>(),
    active: Active[] = [];
  for (const t of doc.transitions ?? []) {
    const left = byId.get(t.leftId),
      right = byId.get(t.rightId),
      key = `${t.leftId}>${t.rightId}`;
    if (!adjacent(left, right) || seen.has(key)) continue;
    seen.add(key);
    const half = Math.floor(t.duration / 2);
    let before: number, after: number;
    if (t.type === "dissolve") {
      before = Math.min(
        half,
        toTimeline(right!, right!.sourceIn),
        duration(left!),
      );
      after = Math.min(
        t.duration - half,
        toTimeline(left!, sourceFrames(left!) - left!.sourceOut),
        duration(right!),
      );
    } else {
      before = Math.min(half, duration(left!));
      after = Math.min(t.duration - half, duration(right!));
    }
    before = Math.max(0, before);
    after = Math.max(0, after);
    if (before + after)
      active.push({ transition: t, cut: right!.start, before, after });
  }
  return active;
}

export interface Plan {
  clips: Clip[];
  active: Active[];
  videoFadeIn: Map<string, number>;
  videoFadeOut: Map<string, number>;
  audioFades: Map<string, { in: number; out: number }>;
  dips: { start: number; before: number; after: number; color: string }[];
}

// Laid-out clips adjusted for dissolves, with fades and dips, as rendered.
export function planTransitions(
  doc: Document,
  sourceFrames: SourceFrames,
): Plan {
  const clips = layout(doc).clips,
    active = activeTransitions(doc, sourceFrames);
  const partner = new Map<string, string>();
  for (const c of clips) {
    const other = c.linkId
      ? clips.find((o) => o.linkId === c.linkId && o.id !== c.id)
      : undefined;
    if (other) partner.set(c.id, other.id);
  }
  const shift = new Map<
    string,
    { start: number; sourceIn: number; sourceOut: number }
  >();
  const update = (id: string, values: Partial<Record<string, number>>) => {
    for (const target of [id, partner.get(id)]) {
      if (!target) continue;
      const s = shift.get(target) ?? { start: 0, sourceIn: 0, sourceOut: 0 };
      shift.set(target, {
        start: s.start + (values.start ?? 0),
        sourceIn: s.sourceIn + (values.sourceIn ?? 0),
        sourceOut: s.sourceOut + (values.sourceOut ?? 0),
      });
    }
  };
  const plan: Plan = {
    clips: [],
    active,
    videoFadeIn: new Map(),
    videoFadeOut: new Map(),
    audioFades: new Map(),
    dips: [],
  };
  const audioFade = (id: string, fadeIn = 0, fadeOut = 0) => {
    const audio = partner.get(id);
    if (!audio) return;
    const current = plan.audioFades.get(audio) ?? { in: 0, out: 0 };
    plan.audioFades.set(audio, {
      in: Math.max(current.in, fadeIn),
      out: Math.max(current.out, fadeOut),
    });
  };
  for (const a of active) {
    const t = a.transition,
      total = activeDuration(a);
    if (t.type === "dissolve") {
      update(t.leftId, { sourceOut: a.after });
      update(t.rightId, { start: -a.before, sourceIn: -a.before });
      plan.videoFadeIn.set(t.rightId, total);
      audioFade(t.leftId, 0, total);
      audioFade(t.rightId, total, 0);
    } else {
      plan.dips.push({
        start: a.cut - a.before,
        before: a.before,
        after: a.after,
        color: t.type === "dip_black" ? "#000000" : "#ffffff",
      });
      audioFade(t.leftId, 0, a.before);
      audioFade(t.rightId, a.after, 0);
    }
  }
  plan.clips = clips.map((c) => {
    const s = shift.get(c.id);
    return s
      ? {
          ...c,
          start: c.start + s.start,
          // Shifts are timeline frames; sources move at the clip's speed.
          sourceIn: c.sourceIn + toSource(c, s.sourceIn),
          sourceOut: c.sourceOut + toSource(c, s.sourceOut),
        }
      : c;
  });
  for (const c of plan.clips) edgeFades(plan, c);
  return plan;
}

// Opacity of a dip colour layer at `frame` (0 outside the dip).
export function dipOpacity(dip: Plan["dips"][number], frame: number): number {
  const f = frame - dip.start;
  if (f < 0 || f >= dip.before + dip.after) return 0;
  return f < dip.before
    ? dip.before
      ? f / dip.before
      : 1
    : 1 - (f - dip.before) / Math.max(1, dip.after);
}

// Gain factor of a clip's audio fades at `frame`.
export function fadeGain(
  fades: { in: number; out: number } | undefined,
  clip: Clip,
  frame: number,
): number {
  if (!fades) return 1;
  const f = frame - clip.start,
    left = duration(clip) - f;
  let gain = 1;
  if (fades.in && f < fades.in) gain = Math.min(gain, f / fades.in);
  if (fades.out && left <= fades.out) gain = Math.min(gain, left / fades.out);
  return Math.max(0, Math.min(1, gain));
}

// The adjacent video clips before and after `id` on its lane.
export function neighbours(doc: Document, id: string) {
  const clips = layout(doc).clips,
    clip = clips.find((c) => c.id === id);
  if (!clip || clip.kind !== "video") return { previous: null, next: null };
  return {
    previous: clips.find((c) => adjacent(c, clip) && c.id !== clip.id) ?? null,
    next: clips.find((c) => adjacent(clip, c) && c.id !== clip.id) ?? null,
  };
}

export function transitionAt(doc: Document, leftId: string, rightId: string) {
  return (doc.transitions ?? []).find(
    (t) => t.leftId === leftId && t.rightId === rightId,
  );
}

// Set (or with a null type, remove) the transition at one cut.
export function setTransition(
  doc: Document,
  leftId: string,
  rightId: string,
  type: TransitionType | null,
  frames: number,
): Document {
  const others = (doc.transitions ?? []).filter(
    (t) => !(t.leftId === leftId && t.rightId === rightId),
  );
  const existing = transitionAt(doc, leftId, rightId);
  return {
    ...doc,
    transitions: type
      ? [
          ...others,
          {
            id: existing?.id ?? uid(),
            leftId,
            rightId,
            type,
            duration: Math.max(1, Math.round(frames)),
          },
        ]
      : others,
  };
}

// Apply one transition to every cut between adjacent video clips (TR-07).
export function setAllTransitions(
  doc: Document,
  type: TransitionType | null,
  frames: number,
): Document {
  const clips = layout(doc).clips;
  let next = doc;
  for (const left of clips)
    for (const right of clips)
      if (left.id !== right.id && adjacent(left, right))
        next = setTransition(next, left.id, right.id, type, frames);
  return next;
}

// Clip edge fades (spec 21), merged with transition fades; capped at the clip length.
function edgeFades(plan: Plan, clip: Clip) {
  const fadeIn = Math.min(clip.fadeIn ?? 0, duration(clip)),
    fadeOut = Math.min(clip.fadeOut ?? 0, duration(clip));
  if (clip.kind === "video") {
    if (fadeIn)
      plan.videoFadeIn.set(
        clip.id,
        Math.max(plan.videoFadeIn.get(clip.id) ?? 0, fadeIn),
      );
    if (fadeOut)
      plan.videoFadeOut.set(
        clip.id,
        Math.max(plan.videoFadeOut.get(clip.id) ?? 0, fadeOut),
      );
  } else if (clip.kind === "audio" && (fadeIn || fadeOut)) {
    const current = plan.audioFades.get(clip.id) ?? { in: 0, out: 0 };
    plan.audioFades.set(clip.id, {
      in: Math.max(current.in, fadeIn),
      out: Math.max(current.out, fadeOut),
    });
  }
}

// Picture opacity of a clip at `frame` from dissolves and edge fades.
export function clipOpacity(plan: Plan, clip: Clip, frame: number): number {
  const fadeIn = plan.videoFadeIn.get(clip.id) ?? 0,
    fadeOut = plan.videoFadeOut.get(clip.id) ?? 0,
    f = frame - clip.start;
  let value = 1;
  if (fadeIn && f < fadeIn) value = Math.min(value, f / fadeIn);
  if (fadeOut && duration(clip) - f <= fadeOut)
    value = Math.min(value, (duration(clip) - f - 1) / fadeOut);
  return Math.max(0, Math.min(1, value));
}

// Set an edge fade on a clip and its linked partner.
export function setFade(
  doc: Document,
  id: string,
  edge: "fadeIn" | "fadeOut",
  frames: number,
): Document {
  const ids = new Set(partners(doc, id).map((c) => c.id));
  return {
    ...doc,
    clips: doc.clips.map((c) =>
      ids.has(c.id) ? { ...c, [edge]: Math.max(0, Math.round(frames)) } : c,
    ),
  };
}
