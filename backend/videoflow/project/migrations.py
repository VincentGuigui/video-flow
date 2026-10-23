"""Forward migrations of raw ``project.json`` dicts.

A migration ``vN -> vN+1`` is a pure function on the JSON dict (camelCase keys), chained
at load time by :func:`migrate`. The store copies the original file to
``project.v<N>.bak.json`` before writing the migrated one.

Compatibility rules (08 §3, corrections to 05 §8):

* Unknown fields and enum values are preserved (``extra='allow'``, open enums), so
  additive changes do not need a version bump.
* ``app.minReader`` is the lowest schema version a reader must understand to write the
  file back. A file whose ``minReader`` is above :data:`SCHEMA_VERSION` is opened
  read-only (:func:`can_write`).
* A file with a ``schemaVersion`` newer than this code is loaded as is (no downgrade).
"""

import copy
from collections.abc import Callable, Mapping
from typing import Any

from videoflow.project.models import SCHEMA_VERSION

type RawProject = dict[str, Any]
type Migration = Callable[[RawProject], RawProject]

MIGRATIONS: Mapping[int, Migration] = {}
"""``{N: migrate_vN_to_vN_plus_1}``. Empty while v1 is the only version."""


class MigrationError(ValueError):
    pass


def schema_version(data: Mapping[str, Any]) -> int:
    version = data.get("schemaVersion")
    if not isinstance(version, int) or isinstance(version, bool) or version < 1:
        raise MigrationError(f"invalid schemaVersion: {version!r}")
    return version


def migrate(
    data: Mapping[str, Any],
    *,
    target: int = SCHEMA_VERSION,
    migrations: Mapping[int, Migration] = MIGRATIONS,
) -> tuple[RawProject, list[int]]:
    """Chain migrations from the file's version up to ``target``.

    Returns the migrated copy and the list of source versions migrated from (empty when
    nothing ran). The input is never modified.
    """
    current = copy.deepcopy(dict(data))
    version = schema_version(current)
    applied: list[int] = []
    while version < target:
        step = migrations.get(version)
        if step is None:
            raise MigrationError(f"no migration from schema v{version} to v{version + 1}")
        current = step(copy.deepcopy(current))
        if schema_version(current) != version + 1:
            raise MigrationError(f"migration from v{version} did not set schemaVersion")
        applied.append(version)
        version += 1
    return current, applied


def min_reader(data: Mapping[str, Any]) -> int:
    app = data.get("app")
    value = app.get("minReader", 1) if isinstance(app, Mapping) else 1
    return value if isinstance(value, int) and not isinstance(value, bool) else 1


def can_write(data: Mapping[str, Any], reader_version: int = SCHEMA_VERSION) -> bool:
    """False when the file needs a newer app to be written back safely."""
    return min_reader(data) <= reader_version
