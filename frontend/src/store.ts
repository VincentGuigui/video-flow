import { create } from "zustand";
import { clone, type Document, type Project, type Settings } from "./model";
import type { Handle, Range } from "./range";
type Command = Record<string, unknown>;
export async function api<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const response = await fetch("/api" + path, {
    ...options,
    headers: { "Content-Type": "application/json", ...options.headers },
  });
  if (!response.ok) {
    const error = await response
      .json()
      .catch(() => ({ detail: response.statusText }));
    throw new Error(
      typeof error.detail === "string"
        ? error.detail
        : JSON.stringify(error.detail),
    );
  }
  return response.json();
}
interface State {
  project: Project | null;
  document: Document;
  selected: string | null;
  focus: string | null;
  frame: number;
  // null follows the default range (focused clip ± 2 s, else the whole edit).
  range: Range | null;
  rangeHandle: Handle | null;
  playing: boolean;
  busy: boolean;
  error: string;
  history: Command[][];
  future: Command[][];
  roots: string[];
  offline: string[];
  load: () => Promise<void>;
  save: (doc: Document, settings?: Settings) => Promise<void>;
  undo: () => Promise<void>;
  redo: () => Promise<void>;
  set: (values: Partial<State>) => void;
}
interface Result {
  project: Project;
  editor: Document;
  inverses: Command[];
  mediaRoots?: string[];
  offline?: string[];
}
export const useEditor = create<State>((set, get) => ({
  project: null,
  document: { version: 1, clips: [] },
  selected: null,
  focus: null,
  frame: 0,
  range: null,
  rangeHandle: null,
  playing: false,
  busy: false,
  error: "",
  history: [],
  future: [],
  roots: [],
  offline: [],
  set: (values) => set(values),
  load: async () => {
    try {
      const r = await api<Result>("/project");
      if (get().project?.id !== r.project.id) {
        pendingClipUpdates.clear();
        clearTimeout(editTimer);
      }
      set({
        ...(get().project?.id !== r.project.id
          ? {
              selected: null,
              focus: null,
              frame: 0,
              range: null,
              rangeHandle: null,
              playing: false,
              history: [],
              future: [],
            }
          : {}),
        project: r.project,
        document: r.editor,
        roots: r.mediaRoots ?? [],
        offline: r.offline ?? [],
      });
    } catch (e) {
      set({ error: String(e) });
    }
  },
  save: async (document, settings) => {
    const state = get();
    if (state.busy || !state.project) return;
    document = applyPending(document);
    pendingClipUpdates.clear();
    clearTimeout(editTimer);
    const original = state.document;
    const commands: Command[] = [{ type: "SetEditor", document }];
    if (settings) commands.push({ type: "SetSettings", settings });
    set({
      document,
      project: settings ? { ...state.project, settings } : state.project,
      busy: true,
      error: "",
    });
    try {
      const r = await api<Result>("/project", {
        method: "PATCH",
        body: JSON.stringify({
          baseRevision: state.project.revision,
          commands,
        }),
      });
      set({
        project: r.project,
        document: r.editor,
        history: [...state.history, r.inverses].slice(-100),
        future: [],
      });
    } catch (e) {
      set({ document: original, error: `Edit was not saved: ${String(e)}` });
      await get().load();
    } finally {
      set({ busy: false });
    }
  },
  undo: async () => {
    await flushClipUpdates();
    const state = get(),
      commands = state.history.at(-1);
    if (!commands || state.busy || !state.project) return;
    set({ busy: true });
    try {
      const r = await api<Result>("/project", {
        method: "PATCH",
        body: JSON.stringify({
          baseRevision: state.project.revision,
          commands,
        }),
      });
      set({
        project: r.project,
        document: r.editor,
        history: state.history.slice(0, -1),
        future: [...state.future, r.inverses],
        selected: null,
        focus: null,
      });
    } catch (e) {
      set({ error: String(e) });
      await get().load();
    } finally {
      set({ busy: false });
    }
  },
  redo: async () => {
    await flushClipUpdates();
    const state = get(),
      commands = state.future.at(-1);
    if (!commands || state.busy || !state.project) return;
    set({ busy: true });
    try {
      const r = await api<Result>("/project", {
        method: "PATCH",
        body: JSON.stringify({
          baseRevision: state.project.revision,
          commands,
        }),
      });
      set({
        project: r.project,
        document: r.editor,
        future: state.future.slice(0, -1),
        history: [...state.history, r.inverses],
      });
    } catch (e) {
      set({ error: String(e) });
      await get().load();
    } finally {
      set({ busy: false });
    }
  },
}));
const pendingClipUpdates = new Map<string, Record<string, unknown>>();
let editTimer: ReturnType<typeof setTimeout> | undefined;
function applyPending(doc: Document) {
  const next = clone(doc);
  for (const [id, values] of pendingClipUpdates) {
    const clip = next.clips.find((c) => c.id === id);
    if (clip) Object.assign(clip, values);
  }
  return next;
}
let flushing: Promise<void> | null = null;
export function flushClipUpdates(): Promise<void> {
  clearTimeout(editTimer);
  if (flushing) return flushing;
  flushing = (async () => {
    while (pendingClipUpdates.size) {
      if (useEditor.getState().busy) {
        await new Promise<void>((resolve) => {
          const unsubscribe = useEditor.subscribe((s) => {
            if (!s.busy) {
              unsubscribe();
              resolve();
            }
          });
        });
        continue;
      }
      const doc = applyPending(useEditor.getState().document);
      pendingClipUpdates.clear();
      await useEditor.getState().save(doc);
      if (pendingClipUpdates.size)
        useEditor
          .getState()
          .set({ document: applyPending(useEditor.getState().document) });
    }
  })().finally(() => {
    flushing = null;
  });
  return flushing;
}
export function updateClip(id: string, values: Record<string, unknown>) {
  const state = useEditor.getState();
  if (!state.document.clips.some((c) => c.id === id)) return;
  pendingClipUpdates.set(id, { ...pendingClipUpdates.get(id), ...values });
  state.set({ document: applyPending(state.document) });
  clearTimeout(editTimer);
  editTimer = setTimeout(() => void flushClipUpdates(), 150);
}
