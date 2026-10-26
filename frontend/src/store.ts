import { create } from "zustand";
import { clone, type Document, type Project, type Settings } from "./model";
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
      set({
        ...(get().project?.id !== r.project.id
          ? {
              selected: null,
              focus: null,
              frame: 0,
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
export function updateClip(id: string, values: Record<string, unknown>) {
  const s = useEditor.getState(),
    doc = clone(s.document);
  const c = doc.clips.find((c) => c.id === id);
  if (c) {
    Object.assign(c, values);
    void s.save(doc);
  }
}
