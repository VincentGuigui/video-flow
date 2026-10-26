import { afterEach, expect, it, vi } from "vitest";
import { useEditor } from "./store";

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
