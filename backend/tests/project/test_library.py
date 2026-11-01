import os
from pathlib import Path

import pytest

from videoflow.project.library import ProjectLibrary, folder_name
from videoflow.project.models import Asset, AssetProbe


def library(tmp_path: Path) -> ProjectLibrary:
    return ProjectLibrary(tmp_path / "app" / "recent-projects.json")


def test_projects_are_named_folders_in_the_working_folder(tmp_path):
    work = tmp_path / "Trip"
    work.mkdir()
    lib = library(tmp_path)
    bundle = lib.create(work, "Day one")
    assert bundle.path == (work / "Day one.video-flow").resolve()
    assert [e["name"] for e in lib.entries()] == ["Day one"]
    assert lib.entries()[0]["folder"] == str(work.resolve())
    with pytest.raises(ValueError, match="already exists"):
        lib.create(work, "Day one")
    with pytest.raises(ValueError):
        lib.create(work, " ")
    with pytest.raises(ValueError, match="not found"):
        lib.create(tmp_path / "missing", "X")
    assert folder_name('a/b:c*?"<>|') == "abc.video-flow"


def test_save_as_copies_beside_the_original_and_keeps_media_relative(tmp_path):
    work = tmp_path / "work"
    (work / "rushes").mkdir(parents=True)
    clip = work / "rushes" / "a.mp4"
    clip.write_bytes(b"x")
    lib = library(tmp_path)
    source = lib.create(work, "Cut")
    project = source.project
    project.assets = [
        Asset(id="ast_a", path=str(clip), content_hash="h", probe=AssetProbe(duration_us=1))
    ]
    source.save(project)
    (source.analysis_dir / "words.json").write_text("{}")
    copy = lib.create(work, "Cut copy", source)
    assert copy.project.id != source.project.id
    assert copy.project.assets[0].rel_path == "rushes/a.mp4"
    assert (copy.analysis_dir / "words.json").read_text() == "{}"
    assert [e["name"] for e in lib.entries()] == ["Cut copy", "Cut"]


def test_rename_moves_the_folder_and_updates_the_list(tmp_path):
    lib = library(tmp_path)
    bundle = lib.create(tmp_path, "Draft")
    (bundle.analysis_dir / "x.json").write_text("{}")
    renamed = lib.rename(bundle, "Final cut")
    assert renamed.path == (tmp_path / "Final cut.video-flow").resolve()
    assert not bundle.path.exists() and (renamed.analysis_dir / "x.json").is_file()
    assert lib.find(renamed.project.id).project.name == "Final cut"
    assert lib.entries()[0]["path"] == str(renamed.path)


def test_recent_list_order_removal_and_latest(tmp_path):
    lib = library(tmp_path)
    assert lib.latest() is None
    first = lib.create(tmp_path, "First")
    second = lib.create(tmp_path, "Second")
    assert lib.latest().project.id == second.project.id
    lib.add(first)
    assert lib.latest().project.id == first.project.id
    lib.remove(first.project.id)
    assert [e["name"] for e in lib.entries()] == ["Second"]
    assert first.path.is_dir()  # removing from the list never deletes files
    os.rename(second.path, tmp_path / "moved.video-flow")
    assert lib.entries() == [] and lib.latest() is None


def test_only_named_project_folders_open(tmp_path):
    import json

    from videoflow.project.library import is_project, open_bundle

    lib = library(tmp_path)
    good = lib.create(tmp_path, "Good")
    assert is_project(good.path)
    plain = tmp_path / "plain"
    plain.mkdir()
    (plain / "project.json").write_text(json.dumps({}))
    assert not is_project(plain)  # project.json alone is not enough
    assert not is_project(tmp_path / "empty.video-flow")
    with pytest.raises(ValueError, match="choose a <name>.video-flow folder"):
        open_bundle(plain)


def test_delete_moves_only_the_project_folder_to_the_trash(tmp_path, monkeypatch):
    import send2trash

    trashed = []
    monkeypatch.setattr(send2trash, "send2trash", trashed.append)
    work = tmp_path / "work"
    work.mkdir()
    (work / "clip.mp4").write_bytes(b"x")
    lib = library(tmp_path)
    bundle = lib.create(work, "Doomed")
    lib.trash(bundle.project.id)
    assert trashed == [str(bundle.path)]
    assert lib.entries() == [] and (work / "clip.mp4").is_file()
    with pytest.raises(ValueError):
        lib.trash("prj_missing")
