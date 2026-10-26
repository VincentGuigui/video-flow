import pytest

from videoflow.project.library import ProjectLibrary
from videoflow.project.models import new_project
from videoflow.project.store import Bundle


def test_save_copy_and_recoverable_delete(tmp_path):
    source = Bundle.create(tmp_path / "Untitled.videoflow", new_project("Untitled"))
    (source.analysis_dir / "words.json").write_text('{"words":[]}')
    library = ProjectLibrary(tmp_path)
    library.rename(source, "My edit")
    assert source.project.name == "My edit"
    copy = library.create("My copy", source)
    assert copy.project.id != source.project.id
    assert (copy.analysis_dir / "words.json").read_text() == '{"words":[]}'
    assert not list(copy.cache_dir.rglob("*.mp4"))
    assert library.find(copy.project.id).project.name == "My copy"
    library.delete(copy.project.id)
    assert len(library.entries()) == 1
    assert list((tmp_path / ".trash").glob("*/project.json"))
    assert source.exists()


def test_names_cannot_escape_project_root(tmp_path):
    library = ProjectLibrary(tmp_path)
    bundle = library.create("../../outside")
    assert bundle.path.parent == tmp_path
    with pytest.raises(ValueError):
        library.find("../../outside")
    with pytest.raises(ValueError):
        library.create(" ")
