import numpy as np

from tests.render import test_render as base
from videoflow.editor.models import EditorClip, EditorDocument, Title, Transform
from videoflow.media import ffmpeg
from videoflow.project.commands import SetEditor
from videoflow.render.graph import compile_graph, write_titles
from videoflow.render.runner import render_project

edit = base.edit  # shared fixture
pixels = base.pixels


def text_clip(identifier: str, start: int, length: int, layer: int, title: Title) -> EditorClip:
    return EditorClip(
        id=identifier,
        kind="text",
        name=title.text,
        start=start,
        source_in=0,
        source_out=length,
        layer=layer,
        title=title,
    )


async def test_titles_render_over_the_picture_in_their_window(edit, tmp_path):
    red = edit.project.assets[0].id
    doc = EditorDocument(
        clips=[
            EditorClip(
                id="red",
                kind="video",
                asset_id=red,
                name="Red",
                start=0,
                source_in=0,
                source_out=50,
                transform=Transform(width=160, height=90),
            ),
            text_clip("title", 10, 20, 1, Title(text="HI", size=0.3)),
            text_clip(
                "lower",
                30,
                15,
                2,
                Title(
                    text="Name\nRole",
                    style="lower_third",
                    size=0.12,
                    box=True,
                    box_color="#0000ff",
                    box_opacity=1,
                ),
            ),
        ]
    )
    project, _ = SetEditor(document=doc).apply(edit.project)
    edit.save(project)
    output = await render_project(edit.project, edit, hw="cpu", normalize=False)
    probe = await ffmpeg.probe(output.path)
    assert probe.video.nb_frames == 50

    def white(frame: np.ndarray) -> int:
        return int((frame.min(axis=2) > 200).sum())

    def blue(frame: np.ndarray) -> int:
        return int(((frame[..., 2] > 200) & (frame[..., 0] < 60)).sum())

    before, during, lower = [await pixels(output.path, f, tmp_path) for f in (5, 20, 40)]
    assert white(before) == 0 and blue(before) == 0
    assert white(during[25:65, 40:120]) > 50  # centred
    assert blue(during) == 0
    assert blue(lower[50:85, :80]) > 150 and blue(lower[:, 100:]) == 0  # lower left
    assert white(lower) > 20


def test_title_graph_reads_one_picture_per_title_and_size(edit, tmp_path):
    same = Title(text="Hello\nWorld")
    doc = EditorDocument(
        clips=[
            text_clip("a", 0, 25, 0, same),
            text_clip("b", 25, 25, 0, same),
            text_clip("c", 50, 10, 0, Title(text="Other")),
        ]
    )
    project, _ = SetEditor(document=doc).apply(edit.project)
    edit.save(project)
    graph = compile_graph(edit.project, "final", tmp_path / "titles")
    assert graph.frames == 60 and len(graph.inputs) == 3 and len(graph.titles) == 2
    assert graph.inputs[0] == graph.inputs[1]
    write_titles(graph)
    for path in graph.titles:
        assert path.parent == tmp_path / "titles" and path.read_bytes()[:4] == b"\x89PNG"
