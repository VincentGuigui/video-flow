"""Server-sent event union (types only; the stream itself is WP14).

One SSE stream per tab; each event carries a monotonically increasing ``seq`` used as
the SSE ``id`` so the client can resume with ``Last-Event-ID``. The union is exported to
OpenAPI ``components/schemas`` for the generated TypeScript client.
"""

from typing import Annotated, Literal

from pydantic import Field, TypeAdapter

from videoflow.core.base import CamelModel
from videoflow.jobs.types import JobDoneEvent, JobProgressEvent


class AssetUpdatedEvent(CamelModel):
    type: Literal["asset.updated"] = "asset.updated"
    project_id: str
    asset_id: str
    parts: list[str] = Field(default_factory=list)
    """What changed: ``probe``, ``proxy``, ``thumbs``, ``peaks``, ``transcript``, ..."""


class ProjectUpdatedEvent(CamelModel):
    type: Literal["project.updated"] = "project.updated"
    project_id: str
    revision: int
    origin: str | None = None
    """Client id that committed the change, so that tab can ignore its own echo."""


type Event = Annotated[
    JobProgressEvent | JobDoneEvent | AssetUpdatedEvent | ProjectUpdatedEvent,
    Field(discriminator="type"),
]


class EventEnvelope(CamelModel):
    seq: int = Field(ge=0)
    event: Event


event_adapter: TypeAdapter[Event] = TypeAdapter(Event)


def parse_event(data: object) -> Event:
    return event_adapter.validate_python(data)
