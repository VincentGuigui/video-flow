"""JSON Schema export of the project and command contracts.

The generated schemas are kept as golden files under ``backend/tests/fixtures/``; a test
fails when the models change without regenerating them::

    uv run python -m videoflow.project.schema --write
"""

import argparse
import json
from pathlib import Path
from typing import Any

from pydantic import TypeAdapter

from videoflow.project.commands import Command
from videoflow.project.models import SCHEMA_VERSION, Project

FIXTURES_DIR = Path(__file__).resolve().parents[2] / "tests" / "fixtures"
PROJECT_SCHEMA_GOLDEN = FIXTURES_DIR / f"project_v{SCHEMA_VERSION}.schema.json"
COMMANDS_SCHEMA_GOLDEN = FIXTURES_DIR / f"commands_v{SCHEMA_VERSION}.schema.json"


def project_json_schema() -> dict[str, Any]:
    schema = Project.model_json_schema(by_alias=True, mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"https://video-flow.local/schema/project.v{SCHEMA_VERSION}.json"
    return schema


def commands_json_schema() -> dict[str, Any]:
    schema = TypeAdapter(list[Command]).json_schema(by_alias=True, mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["title"] = "CommandBatch"
    return schema


def dumps_schema(schema: dict[str, Any]) -> str:
    return json.dumps(schema, indent=2, ensure_ascii=False, sort_keys=True) + "\n"


def write_goldens() -> list[Path]:
    written = []
    for path, schema in (
        (PROJECT_SCHEMA_GOLDEN, project_json_schema()),
        (COMMANDS_SCHEMA_GOLDEN, commands_json_schema()),
    ):
        path.write_text(dumps_schema(schema), encoding="utf-8", newline="\n")
        written.append(path)
    return written


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Print or write the project JSON Schemas.")
    parser.add_argument("--write", action="store_true", help="regenerate the golden files")
    args = parser.parse_args(argv)
    if args.write:
        for path in write_goldens():
            print(path)
    else:
        print(dumps_schema(project_json_schema()), end="")


if __name__ == "__main__":
    main()
