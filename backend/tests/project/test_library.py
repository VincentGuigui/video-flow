import pytest

from videoflow.project.library import ProjectLibrary
from videoflow.project.models import new_project
from videoflow.project.store import Bundle


def test_save_copy_and_recoverable_delete(tmp_path):
    source = Bundle.create(tmp_path / "Untitled.videoflow", new_project("Untitled"))
    (source.analysis_dir / "words.json").write_text('{"words":[]}')
    library = ProjectLibrary(tmp_path)
    source = library.rename(source, "My edit")
    assert source.project.name == "My edit"
    assert source.path.name.startswith("My edit-") and source.path.suffix == ".videoflow"
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


def test_rename_moves_the_folder_and_keeps_its_suffix(tmp_path):
    library = ProjectLibrary(tmp_path)
    bundle = library.create("Draft")
    (bundle.cache_dir / "proxies" / "p.mp4").write_bytes(b"x")
    suffix = bundle.path.stem.rsplit("-", 1)[1]
    renamed = library.rename(bundle, "Final cut")
    assert renamed.path == tmp_path / f"Final cut-{suffix}.videoflow"
    assert not bundle.path.exists()
    assert (renamed.cache_dir / "proxies" / "p.mp4").read_bytes() == b"x"
    assert library.find(renamed.project.id).project.name == "Final cut"
    other = library.rename(library.create("Other"), "Final cut")
    assert other.path != renamed.path  # same name, distinct folders


def test_latest_is_the_most_recently_saved_project(tmp_path):
    import os

    library = ProjectLibrary(tmp_path)
    assert library.latest() is None
    first, second = library.create("First"), library.create("Second")
    os.utime(first.project_file, (1, 1))
    assert library.latest().project.id == second.project.id
