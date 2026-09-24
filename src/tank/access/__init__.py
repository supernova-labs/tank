"""Tank 0.2 — the access trail.

An access tool is an async function a consumer decorates. Tank opens and closes
the boundary of the call, measures it, classifies any exception without
altering it, checks that the return is `list[<returns>]` and MARKS it when it
is not, and writes exactly one event plus one row per unit returned.

    registry = Registry(ontology)

    @registry.access_tool(
        name="news_by_entity",
        version="1.0.0",
        returns=Candidate,
        via="own",
        scope="entity",
        scope_from="entity_id",
    )
    async def news_by_entity(entity_id: str, limit: int = 20) -> list[Candidate]:
        rows = await my_own_query(...)
        return refs_from(rows, type="news", stage=Candidate)

The tenant binds separately, at the call:

    async with session(registry, sink, ns="acme", db="tank", run_id="conv-7/msg-3"):
        await news_by_entity("entity:e1")

This slice writes `capture_mode="direct"`: the boundary, the timing, the error,
the scope value and the references. The gateway, which reads the query plan and
raises the mode to `gateway_plan`, is the other half and is not here yet — and
`obs.plan` says `below_mode` on every event rather than leaving a field empty.
"""

from tank.access.context import Session, session
from tank.access.event import (
    AccessEvent,
    AccessRefRow,
    DropCounter,
    EventSink,
    MemorySink,
    Observability,
    SurrealSink,
)
from tank.access.registry import DeclarationError, Registry, ToolDescriptor
from tank.access.types import Candidate, Evidence, Ref, refs_from

__all__ = [
    "AccessEvent",
    "AccessRefRow",
    "Candidate",
    "DeclarationError",
    "DropCounter",
    "EventSink",
    "Evidence",
    "MemorySink",
    "Observability",
    "Ref",
    "Registry",
    "Session",
    "SurrealSink",
    "ToolDescriptor",
    "refs_from",
    "session",
]
