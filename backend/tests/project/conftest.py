import json
from pathlib import Path
from typing import Any

import pytest

from videoflow.project.models import Project

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
FULL_FIXTURE = FIXTURES / "project_v1_full.json"


def load_fixture_dict() -> dict[str, Any]:
    data: dict[str, Any] = json.loads(FULL_FIXTURE.read_text(encoding="utf-8"))
    return data


@pytest.fixture
def raw_project() -> dict[str, Any]:
    return load_fixture_dict()


@pytest.fixture
def project() -> Project:
    return Project.model_validate(load_fixture_dict())
