"""Base model and open enums shared by every serialised contract.

All contracts serialise to camelCase JSON (``model_dump(by_alias=True)``) and keep
unknown fields (``extra='allow'``) so that a file written by a newer version survives a
load/save cycle in an older one. Enum-like fields are *open*: a value the current code
does not know is kept as an :class:`UnknownValue` instead of failing validation.
"""

from typing import Any

from pydantic import BaseModel, ConfigDict, GetCoreSchemaHandler
from pydantic.alias_generators import to_camel
from pydantic_core import core_schema


class CamelModel(BaseModel):
    """Base for every contract model: camelCase aliases, unknown fields preserved."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        extra="allow",
    )

    def dump(self) -> dict[str, Any]:
        """JSON-compatible dict with camelCase keys (the on-disk and wire form)."""
        return self.model_dump(mode="json", by_alias=True)


class UnknownValue(str):
    """An enum value written by a newer schema, kept verbatim and written back as is."""

    __slots__ = ()

    @classmethod
    def __get_pydantic_core_schema__(
        cls, source: Any, handler: GetCoreSchemaHandler
    ) -> core_schema.CoreSchema:
        return core_schema.no_info_after_validator_function(
            cls,
            core_schema.str_schema(min_length=1),
            serialization=core_schema.plain_serializer_function_ser_schema(str),
        )

    def __repr__(self) -> str:
        return f"UnknownValue({str.__repr__(self)})"


def is_unknown(value: object) -> bool:
    """True when an open-enum field holds a value this version does not know."""
    return isinstance(value, UnknownValue)
