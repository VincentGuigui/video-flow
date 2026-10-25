import pytest
from pydantic import ValidationError

from tests.timeline.builders import ProjectBuilder, S, clip
from videoflow.editor.models import EditorClip, EditorDocument, Transform, layout
from videoflow.editor.resolve import document_for, editable_document
from videoflow.exporters.otio_compile import compile_timeline
from videoflow.project.commands import SetEditor, apply_batch
from videoflow.timeline.resolve import resolve


def item(id="v", kind="video", **values):
    return EditorClip(id=id, kind=kind, asset_id="a", name="Take", start=0,
                      source_in=0, source_out=30, **values)


def test_layout_compacts_only_uncovered_time_and_keeps_explicit_gaps():
    first = item()
    second = item("v2").model_copy(update={"start": 100})
    doc = EditorDocument(clips=[first, second])
    clips, total = layout(doc)
    assert [c.start for c in clips] == [0, 30]
    assert total == 60
    gap = EditorClip(id="gap", kind="gap", name="Empty", start=30,
                     source_in=0, source_out=70)
    clips, total = layout(EditorDocument(clips=[first, gap, second]))
    assert total == 130
    assert clips[-1].start == 100


def test_disabled_layers_do_not_extend_or_erase_enabled_layers():
    doc = EditorDocument(clips=[item(), item("upper", layer=1),
                               item("disabled", enabled=False).model_copy(update={"start": 100})])
    clips, total = layout(doc)
    assert total == 30
    assert [c.id for c in clips] == ["v", "upper"]


def test_link_requires_one_video_one_audio_with_identical_timing():
    video = item(link_id="pair")
    with pytest.raises(ValidationError, match="one video and one audio"):
        EditorDocument(clips=[video])
    with pytest.raises(ValidationError, match="same timing"):
        EditorDocument(clips=[video, item("a", "audio", link_id="pair").model_copy(update={"start": 5})])
    assert len(EditorDocument(clips=[video, item("a", "audio", link_id="pair")]).clips) == 2


@pytest.mark.parametrize("values", [{"x": float("nan")}, {"width": float("inf")},
                                    {"crop_left": .6, "crop_right": .5}])
def test_invalid_transforms_are_rejected(values):
    with pytest.raises(ValidationError):
        Transform(**values)


def test_editor_command_round_trip_resolves_layers_and_empty_clips():
    project = ProjectBuilder().asset("a", 10*S).build()
    gap = EditorClip(id="g", kind="gap", name="Empty", start=30, source_in=0, source_out=30)
    doc = EditorDocument(clips=[item(link_id="pair"), item("a1", "audio", link_id="pair"),
                               item("upper", layer=1), gap])
    updated, inverse = apply_batch(project, [SetEditor(document=doc)])
    assert document_for(updated) == doc
    timeline = resolve(updated)
    assert timeline.duration == 60
    assert len([t for t in timeline.tracks if t.kind == "video"]) == 2
    assert timeline.track("V1").clips[-1].asset_id == "__gap__"
    otio = compile_timeline(timeline, updated)
    assert otio.duration().value == 60
    restored, _ = apply_batch(updated, inverse)
    restored.revision = project.revision
    assert restored.dump() == project.dump()


def test_source_bounds_checked_before_project_changes():
    project = ProjectBuilder().asset("a", S).build()
    invalid = EditorDocument(clips=[item().model_copy(update={"source_out": 31})])
    with pytest.raises(ValueError, match="exceeds"):
        SetEditor(document=invalid).apply(project)
    assert document_for(project) is None


def test_legacy_edit_is_converted_without_losing_authored_cuts():
    project = ProjectBuilder().asset("a", 10*S).beat("beat", clip("old", "a", S, 3*S)).build()
    doc = editable_document(project)
    assert {c.kind for c in doc.clips} == {"video", "audio"}
    assert {c.source_in for c in doc.clips} == {30}
    assert doc.clips[0].link_id == doc.clips[1].link_id
    assert document_for(project) is None
