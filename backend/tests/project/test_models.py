import copy
import json
from typing import Any

import jsonschema
import pytest
from pydantic import ValidationError

from tests.project.conftest import FIXTURES
from videoflow.core.base import UnknownValue, is_unknown
from videoflow.project import schema
from videoflow.project.models import (
    BeatAnchor,
    FitRect,
    Project,
    invariant_violations,
    new_project,
)
from videoflow.project.store import Bundle


def _validator() -> jsonschema.Draft202012Validator:
    golden = json.loads(schema.PROJECT_SCHEMA_GOLDEN.read_text(encoding="utf-8"))
    return jsonschema.Draft202012Validator(golden)


def test_project_schema_golden_is_current() -> None:
    golden = schema.PROJECT_SCHEMA_GOLDEN.read_text(encoding="utf-8")
    assert schema.dumps_schema(schema.project_json_schema()) == golden, (
        "project schema changed: run `uv run python -m videoflow.project.schema --write`"
    )


def test_commands_schema_golden_is_current() -> None:
    golden = schema.COMMANDS_SCHEMA_GOLDEN.read_text(encoding="utf-8")
    assert schema.dumps_schema(schema.commands_json_schema()) == golden


def test_fixture_validates_against_golden_schema(raw_project: dict[str, Any]) -> None:
    jsonschema.Draft202012Validator.check_schema(_validator().schema)
    _validator().validate(raw_project)


def test_new_project_validates_against_golden_schema() -> None:
    _validator().validate(new_project("Empty").dump())


def test_fixture_is_canonical_and_consistent(raw_project: dict[str, Any], project: Project) -> None:
    assert project.dump() == raw_project
    assert invariant_violations(project) == []
    assert isinstance(project.overlays[0].anchor, BeatAnchor)
    assert isinstance(project.overlays[1].fit, FitRect)
    assert project.assets[3].probe.video is None
    assert not project.assets[2].probe.has_audio


def test_main_line_and_dormant_rule(project: Project) -> None:
    line = [c.id for _, c in project.main_line()]
    assert len(line) == 4  # the off-topic beat is excluded
    active = [project.is_transition_active(t) for t in project.transitions]
    assert active == [True, True, False]


def _with_unknowns(raw: dict[str, Any]) -> dict[str, Any]:
    data = copy.deepcopy(raw)
    data["futureTopLevel"] = {"nested": [1, 2, {"x": None}]}
    data["settings"]["futureSetting"] = "on"
    data["settings"]["llmProvider"] = "mistral-cloud"
    data["assets"][0]["probe"]["video"]["hdr"] = "dolby_vision"
    data["assets"][0]["probe"]["futureProbe"] = 3.5
    data["beats"][0]["role"] = "teaser"
    data["beats"][0]["futureBeatField"] = True
    data["beats"][1]["takes"][0]["status"] = "maybe"
    data["beats"][1]["cut"][0]["audio"]["mode"] = "ducked"
    data["beats"][1]["cut"][0]["futureItem"] = {"a": 1}
    data["transitions"][0]["type"] = "page_curl"
    data["transitions"][0]["alignment"] = "custom"
    data["transitions"][2]["audio"] = "j_cut"
    data["overlays"][0]["track"] = "V3"
    data["overlays"][0]["fit"] = "stretch"
    data["constraints"][0]["type"] = "should_link"
    data["overrides"]["futureOverride"] = []
    return data


def test_round_trip_keeps_unknown_fields_and_enum_values(raw_project: dict[str, Any]) -> None:
    data = _with_unknowns(raw_project)
    project = Project.model_validate(data)
    assert is_unknown(project.beats[0].role)
    assert project.beats[0].role == "teaser"
    assert isinstance(project.transitions[0].type, UnknownValue)
    assert project.dump() == data


def test_round_trip_through_bundle(tmp_path: Any, raw_project: dict[str, Any]) -> None:
    data = _with_unknowns(raw_project)
    bundle = Bundle.create(tmp_path / "p.videoflow", Project.model_validate(data))
    loaded = Bundle(bundle.path).load()
    assert loaded.dump() == data
    on_disk = json.loads(bundle.project_file.read_text(encoding="utf-8"))
    assert on_disk == data


def test_invalid_ranges_rejected(raw_project: dict[str, Any]) -> None:
    data = copy.deepcopy(raw_project)
    item = data["beats"][0]["cut"][0]
    item["sourceOutUs"] = item["sourceInUs"]
    with pytest.raises(ValidationError):
        Project.model_validate(data)


def test_invariant_violations_detected(project: Project) -> None:
    broken = project.model_copy(deep=True)
    broken.beats[1].takes[1].status = "selected"
    broken.beats[2].cut[0].id = broken.beats[0].cut[0].id
    broken.overlays[0].asset_id = "ast_missing"
    broken.sync_groups[0].members.append(broken.sync_groups[0].members[0])
    problems = invariant_violations(broken)
    assert any("more than one selected" in p for p in problems)
    assert any("duplicate clip item" in p for p in problems)
    assert any("missing asset ast_missing" in p for p in problems)
    assert any("more than one sync group" in p for p in problems)


def test_fixture_files_present() -> None:
    assert (FIXTURES / "project_v1_full.json").is_file()
    assert schema.PROJECT_SCHEMA_GOLDEN.is_file()
