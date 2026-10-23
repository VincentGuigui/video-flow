import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import Any

import pytest

from videoflow.project.commands import BladeItem, MoveBeat, RenameProject
from videoflow.project.migrations import MigrationError, migrate
from videoflow.project.models import Project
from videoflow.project.store import (
    Bundle,
    HistoryEntry,
    ProjectStoreError,
    ReadOnlyProjectError,
    StaleRevisionError,
    save_atomic,
)

BACKEND = Path(__file__).resolve().parents[2]


def _write_raw(bundle: Bundle, data: dict[str, Any]) -> None:
    bundle.path.mkdir(parents=True, exist_ok=True)
    bundle.project_file.write_text(json.dumps(data), encoding="utf-8")


def test_create_lays_out_the_bundle(tmp_path: Path, project: Project) -> None:
    bundle = Bundle.create(tmp_path / "Unboxing.videoflow", project)
    for folder in bundle.directories():
        assert folder.is_dir()
    assert bundle.project_file.is_file()
    assert Bundle(bundle.path).load() == project
    with pytest.raises(ProjectStoreError):
        Bundle.create(bundle.path, project)


def _v1_to_v2(data: dict[str, Any]) -> dict[str, Any]:
    """Dummy migration: rename ``name`` to ``title`` and bump the version."""
    data["schemaVersion"] = 2
    data["title"] = data["name"]
    data["name"] = data["name"].upper()
    return data


def test_dummy_migration_keeps_a_backup(tmp_path: Path, raw_project: dict[str, Any]) -> None:
    bundle = Bundle(tmp_path / "m.videoflow")
    _write_raw(bundle, raw_project)
    original = bundle.project_file.read_bytes()

    project = bundle.load(migrations={1: _v1_to_v2}, target_version=2)

    assert bundle.migrated_from == [1]
    assert project.schema_version == 2
    assert project.name == "UNBOXING X200"
    assert project.model_extra == {"title": "Unboxing X200"}
    assert bundle.backup_file(1).read_bytes() == original
    on_disk = json.loads(bundle.project_file.read_text(encoding="utf-8"))
    assert on_disk["schemaVersion"] == 2 and on_disk["title"] == "Unboxing X200"
    # Loading again does not migrate twice nor overwrite the backup.
    again = Bundle(bundle.path)
    assert again.load(migrations={1: _v1_to_v2}, target_version=2) == project
    assert again.migrated_from == []
    assert bundle.backup_file(1).read_bytes() == original


def test_migrate_is_pure_and_checks_versions(raw_project: dict[str, Any]) -> None:
    snapshot = json.dumps(raw_project)
    migrated, applied = migrate(raw_project, target=2, migrations={1: _v1_to_v2})
    assert applied == [1] and migrated["schemaVersion"] == 2
    assert json.dumps(raw_project) == snapshot
    with pytest.raises(MigrationError):
        migrate(raw_project, target=3, migrations={1: _v1_to_v2})
    with pytest.raises(MigrationError):
        migrate(raw_project, target=2, migrations={1: lambda d: d})
    with pytest.raises(MigrationError):
        migrate({"schemaVersion": "1"})


def test_newer_min_reader_is_read_only(tmp_path: Path, raw_project: dict[str, Any]) -> None:
    data = dict(raw_project, schemaVersion=3, app={"writer": "videoflow 9", "minReader": 3})
    data["newThing"] = {"x": 1}
    bundle = Bundle(tmp_path / "ro.videoflow")
    _write_raw(bundle, data)
    project = bundle.load()
    assert bundle.read_only
    assert project.model_extra == {"newThing": {"x": 1}}
    with pytest.raises(ReadOnlyProjectError):
        bundle.save(project)
    with pytest.raises(ReadOnlyProjectError):
        bundle.commit(project.revision, [RenameProject(name="x")])
    assert json.loads(bundle.project_file.read_text(encoding="utf-8")) == data


def test_newer_schema_with_compatible_min_reader_is_writable(
    tmp_path: Path, raw_project: dict[str, Any]
) -> None:
    data = dict(raw_project, schemaVersion=2, extraV2Field=[1])
    bundle = Bundle(tmp_path / "v2.videoflow")
    _write_raw(bundle, data)
    project = bundle.load()
    assert not bundle.read_only
    updated, _ = bundle.commit(project.revision, [RenameProject(name="Renamed")])
    on_disk = json.loads(bundle.project_file.read_text(encoding="utf-8"))
    assert on_disk["schemaVersion"] == 2 and on_disk["extraV2Field"] == [1]
    assert on_disk["name"] == "Renamed" == updated.name


def test_save_atomic_replaces_content(tmp_path: Path) -> None:
    target = tmp_path / "f.json"
    save_atomic(target, b"one")
    save_atomic(target, b"two")
    assert target.read_bytes() == b"two"
    assert list(tmp_path.iterdir()) == [target]


def test_save_atomic_failure_keeps_old_file(tmp_path: Path) -> None:
    target = tmp_path / "f.json"
    save_atomic(target, b"old")

    def boom(tmp: Path) -> None:
        assert tmp.read_bytes() == b"new"
        raise OSError("disk unplugged")

    with pytest.raises(OSError):
        save_atomic(target, b"new", before_replace=boom)
    assert target.read_bytes() == b"old"
    assert list(tmp_path.iterdir()) == [target]


def test_atomic_save_survives_a_crash_between_write_and_rename(
    tmp_path: Path, project: Project
) -> None:
    bundle = Bundle.create(tmp_path / "crash.videoflow", project)
    before = bundle.project_file.read_bytes()
    script = textwrap.dedent(
        """
        import os, sys
        from pathlib import Path
        from videoflow.project.store import Bundle, dumps_project, save_atomic

        bundle = Bundle(Path(sys.argv[1]))
        project = bundle.load()
        project.name = "never saved"

        def die(tmp):
            os._exit(9)  # hard kill: no cleanup, no finally blocks

        save_atomic(bundle.project_file, dumps_project(project), before_replace=die)
        """
    )
    result = subprocess.run(
        [sys.executable, "-c", script, str(bundle.path)],
        cwd=BACKEND,
        env={**os.environ, "PYTHONPATH": str(BACKEND)},
        capture_output=True,
        timeout=60,
    )
    assert result.returncode == 9, result.stderr.decode()
    assert bundle.project_file.read_bytes() == before
    leftovers = list(bundle.path.glob(".*.tmp"))
    assert len(leftovers) == 1  # the torn temp file is still there ...
    reloaded = Bundle(bundle.path).load()
    assert reloaded == project
    assert not list(bundle.path.glob(".*.tmp"))  # ... and cleaned on the next load


def test_commit_appends_history_and_checks_revision(tmp_path: Path, project: Project) -> None:
    bundle = Bundle.create(tmp_path / "c.videoflow", project)
    demo = next(b for b in project.beats if b.label == "Démo du chargeur")
    updated, inverses = bundle.commit(project.revision, [MoveBeat(beat_id=demo.id, to_index=0)])
    assert updated.revision == project.revision + 1 == bundle.revision()
    assert Bundle(bundle.path).load() == updated

    with pytest.raises(StaleRevisionError) as err:
        bundle.commit(project.revision, [RenameProject(name="lost update")])
    assert err.value.current_revision == updated.revision

    undone, _ = bundle.commit(updated.revision, inverses)
    assert undone.model_copy(update={"revision": project.revision}) == project

    history = bundle.read_history()
    assert [h.revision for h in history] == [project.revision + 1, project.revision + 2]
    assert all(h.schema_version == 1 for h in history)
    line = json.loads(bundle.history_file.read_text(encoding="utf-8").splitlines()[0])
    assert set(line) == {"schemaVersion", "revision", "baseRevision", "at", "commands", "inverses"}


def test_history_is_replayed_after_a_crash_before_save(tmp_path: Path, project: Project) -> None:
    bundle = Bundle.create(tmp_path / "wal.videoflow", project)
    item = project.beats[0].cut[0]
    cmds = [BladeItem(item_id=item.id, at_us=3_000_000)]
    # Simulate: the history line was fsynced, then the process died before the save.
    bundle.append_history(
        HistoryEntry(
            revision=project.revision + 1,
            base_revision=project.revision,
            commands=cmds,
            inverses=[],
        )
    )
    with open(bundle.history_file, "ab") as fh:
        fh.write(b'{"schemaVersion":1,"revision":')  # torn last line
    reloaded = Bundle(bundle.path).load()
    assert reloaded.revision == project.revision + 1
    assert len(reloaded.beats[0].cut) == 2
    on_disk = Project.model_validate_json(bundle.project_file.read_bytes())
    assert on_disk == reloaded


def test_invalid_files_are_reported(tmp_path: Path) -> None:
    bundle = Bundle(tmp_path / "bad.videoflow")
    bundle.path.mkdir()
    bundle.project_file.write_text("{not json", encoding="utf-8")
    with pytest.raises(ProjectStoreError):
        bundle.load()
    bundle.project_file.write_text('{"schemaVersion": 1, "id": "prj_x"}', encoding="utf-8")
    with pytest.raises(ProjectStoreError):
        bundle.load()
