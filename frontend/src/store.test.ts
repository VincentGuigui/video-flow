import { afterEach, expect, it, vi } from "vitest";
import { useEditor, updateClip, flushClipUpdates } from "./store";
import { defaultTransform, clone } from "./model";

const initial = useEditor.getState();
afterEach(() => {
  vi.unstubAllGlobals();
  useEditor.setState(initial, true);
});
const response = (id: string) =>
  new Response(
    JSON.stringify({
      project: {
        id,
        name: id,
        revision: 0,
        assets: [],
        settings: { width: 1920, height: 1080, frameRate: { num: 30, den: 1 } },
      },
      editor: { version: 1, clips: [] },
    }),
  );

it("clears old project selection and undo history after deleting the open project", async () => {
  vi.stubGlobal(
    "fetch",
    vi
      .fn()
      .mockResolvedValueOnce(response("original"))
      .mockResolvedValueOnce(response("new-untitled")),
  );
  await useEditor.getState().load();
  useEditor.setState({
    selected: "old-clip",
    focus: "old-clip",
    frame: 100,
    playing: true,
    history: [[{ type: "SetEditor" }]],
    future: [[{ type: "SetEditor" }]],
  });
  await useEditor.getState().load();
  expect(useEditor.getState()).toMatchObject({
    selected: null,
    focus: null,
    frame: 0,
    playing: false,
    history: [],
    future: [],
  });
});

it("keeps history when reloading the same project after an import", async () => {
  vi.stubGlobal(
    "fetch",
    vi
      .fn()
      .mockResolvedValueOnce(response("same"))
      .mockResolvedValueOnce(response("same")),
  );
  await useEditor.getState().load();
  useEditor.setState({ history: [[{ type: "SetEditor" }]] });
  await useEditor.getState().load();
  expect(useEditor.getState().history).toHaveLength(1);
});

it("previews numeric edits immediately and saves edits entered during an in-flight request", async () => {
  await Promise.resolve();
  const project = await response("properties").json();
  const clip = {
    id: "v",
    kind: "video" as const,
    assetId: "a",
    name: "Video",
    start: 0,
    sourceIn: 0,
    sourceOut: 30,
    layer: 0,
    enabled: true,
    linkId: null,
    gainDb: 0,
    transform: defaultTransform(),
  };
  useEditor.setState({
    project: project.project,
    document: { version: 1, clips: [clip] },
  });
  let firstResolve: ((response: Response) => void) | undefined;
  const documents: unknown[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn((_url, options) => {
      const body = JSON.parse(options.body);
      const document = body.commands[0].document;
      documents.push(clone(document));
      const result = new Response(
        JSON.stringify({
          project: { ...project.project, revision: documents.length },
          editor: document,
          inverses: [{ type: "SetEditor" }],
        }),
      );
      if (documents.length === 1)
        return new Promise<Response>((resolve) => {
          firstResolve = () => resolve(result);
        });
      return Promise.resolve(result);
    }),
  );
  updateClip("v", { transform: { ...clip.transform, x: 10 } });
  expect(useEditor.getState().document.clips[0].transform.x).toBe(10);
  const pending = flushClipUpdates();
  updateClip("v", {
    transform: { ...useEditor.getState().document.clips[0].transform, y: 25 },
  });
  expect(useEditor.getState().document.clips[0].transform.y).toBe(25);
  firstResolve!(new Response());
  await pending;
  expect(documents).toHaveLength(2);
  expect(useEditor.getState().document.clips[0].transform).toMatchObject({
    x: 10,
    y: 25,
  });
  expect(useEditor.getState().busy).toBe(false);
});
