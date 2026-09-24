"""The event, and the sink that writes it.

One `tank_access_event` per tool call, plus one `tank_access_ref` per unit the
tool returned. The shape here mirrors `migrations/0001_access.surql` field for
field, and it has to: the core columns are non-`option` with no backfill, so an
event this module builds wrong is refused by the server rather than stored
wrong. That is the point — the guarantee is in the DDL, not in this file's
discipline.

Nothing here ever raises into the caller. A failure to record an access is a
failure of the instrument, and the subject's result propagates untouched; the
drop is logged out of band and counted. That is `on_fail="mark"` carried into
runtime, and it is why `DropCounter` exists instead of a bare `except: pass`.
"""

from __future__ import annotations

import json
import logging
from collections import Counter
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:  # pragma: no cover - typing only
    from tank.access.context import Session

__all__ = [
    "AccessEvent",
    "AccessRefRow",
    "DropCounter",
    "EventSink",
    "MemorySink",
    "Observability",
    "SurrealSink",
]

log = logging.getLogger("tank.access")

CaptureMode = Literal["direct", "gateway", "gateway_plan", "typed"]
Attribution = Literal["in_frame", "stale", "none"]


class Observability(BaseModel):
    """The event's record of its own observability.

    Six closed vocabularies, one per dimension that depends on the capture tier
    or on policy. Every one of them is required: this is not a bag of optional
    flags, it is the field that says WHY something is absent. A dimension that
    claims 'observed' over a field that is not there is refused by the database.
    """

    model_config = ConfigDict(extra="forbid")

    scope: Literal["observed", "unbound", "undeclared", "expired"]
    plan: Literal[
        "observed",
        "partial",
        "unsupported_statement",
        "below_mode",
        "server_unsupported",
        "unknown_shape",
        "disabled",
        "expired",
    ]
    args: Literal["observed", "shape_only", "redacted", "expired"]
    error_message: Literal["observed", "not_applicable", "redacted", "expired"]
    skill: Literal["reported", "none", "not_reported"]
    refs: Literal["observed", "undeclared_stage", "normalize_failed", "below_mode", "expired"]


class AccessEvent(BaseModel):
    """One tool call, in the shape the table accepts."""

    model_config = ConfigDict(extra="forbid")

    ts: str
    latency_ns: int
    tank_version: str
    ontology_version: str
    ontology_hash: str
    run_id: str
    sample_rate: float
    capture_mode: CaptureMode
    attribution: Attribution
    caller_kind: str
    error_class: str
    args_shape: list[dict[str, str]] = Field(default_factory=list)
    obs: Observability

    tool: str | None = None
    tool_version: str | None = None
    tool_fingerprint: str | None = None
    stage: str | None = None
    n_refs: int | None = None
    scope: str | None = None
    scope_value: str | None = None
    error_type: str | None = None
    error_message: str | None = None
    skill_version: str | None = None
    conversation_id: str | None = None
    message_id: str | None = None
    server_version: str | None = None


class AccessRefRow(BaseModel):
    """One unit a tool returned."""

    model_config = ConfigDict(extra="forbid")

    ts: str
    unit_type: str
    unit_key: str
    stage: Literal["candidate", "evidence"]
    tool: str | None = None
    unit: str | None = None
    rank: int | None = None
    score: float | None = None
    unit_version: str | None = None
    content_hash: str | None = None


@dataclass
class DropCounter:
    """Why events were not written, counted by reason.

    A drop that is only logged is a drop nobody sees. The reasons are kept apart
    because "the table is missing" and "the write was refused" call for
    different actions, and collapsing them into one silent zero is exactly the
    failure this project exists to prevent. This counter is per process; moving
    it out of the process is what makes `OBS-002` safe to fire, and that is 0.3.
    """

    reasons: Counter[str] = field(default_factory=Counter)

    def drop(self, reason: str, exc: BaseException | None = None) -> None:
        self.reasons[reason] += 1
        log.warning("tank: access event dropped (%s): %s", reason, exc)

    @property
    def total(self) -> int:
        return sum(self.reasons.values())


class EventSink(Protocol):
    """Where events go. The decorator never calls this directly without a guard."""

    drops: DropCounter

    async def write(
        self, session: Session, event: AccessEvent, refs: list[AccessRefRow]
    ) -> bool: ...


class MemorySink:
    """Keeps events in a list. For tests, and for seeing the shape of the thing."""

    def __init__(self) -> None:
        self.events: list[AccessEvent] = []
        self.refs: list[AccessRefRow] = []
        self.drops = DropCounter()

    async def write(self, session: Session, event: AccessEvent, refs: list[AccessRefRow]) -> bool:
        self.events.append(event)
        self.refs.extend(refs)
        return True


def _literal(value: object) -> str:
    """Render a Python value as a SurrealQL literal.

    Only the types the event actually carries. Anything else is a programming
    error here rather than a value to coerce, because a silently coerced field
    is how a wrong number gets stored.
    """
    if value is None:
        return "NONE"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, str):
        # json.dumps gives correct escaping for quotes, backslashes and control
        # characters, and SurrealQL accepts double-quoted strings. Hand-rolled
        # quoting here would be an injection surface in the one place that
        # writes the consumer's own database.
        return json.dumps(value)
    if isinstance(value, list):
        return "[" + ", ".join(_literal(v) for v in value) + "]"
    if isinstance(value, dict):
        return "{" + ", ".join(f"{k}: {_literal(v)}" for k, v in value.items()) + "}"
    raise TypeError(f"no SurrealQL literal for {type(value).__name__}")


class SurrealSink:
    """Writes through the caller's own connection, into the caller's own (ns, db).

    The guard is not optional and not belt-and-braces. A `CREATE` against a
    table that does not exist SUCCEEDS on SurrealDB and fabricates a
    `TYPE ANY SCHEMALESS` table, so a tenant that was never migrated would have
    its first event invent a schema with none of the invariants — and the core,
    which has no backfill, would evaporate on that first write. So the sink
    checks once per (ns, db) that the table is there and SCHEMAFULL, refuses to
    write when it is not, and does not bring the call down.
    """

    def __init__(self, execute: Any) -> None:
        #: async callable (sql, ns, db) -> list of statement results
        self._execute = execute
        self.drops = DropCounter()
        self._checked: dict[tuple[str, str], bool] = {}

    async def _table_is_ready(self, session: Session) -> bool:
        key = (session.ns, session.db)
        if key in self._checked:
            return self._checked[key]
        try:
            info = await self._execute("INFO FOR DB;", session.ns, session.db)
            tables = (info[0].get("result") or {}).get("tables", {})
            ddl = tables.get("tank_access_event", "")
            ready = bool(ddl) and "SCHEMAFULL" in ddl
        except Exception as exc:  # noqa: BLE001 - an unreachable database is a drop, not a crash
            self.drops.drop("bootstrap_failed", exc)
            return False
        self._checked[key] = ready
        if not ready:
            self.drops.drop("table_missing")
        return ready

    async def write(self, session: Session, event: AccessEvent, refs: list[AccessRefRow]) -> bool:
        if not await self._table_is_ready(session):
            return False
        payload = event.model_dump(exclude_none=True)
        # Nanoseconds, integral. SurrealQL has no fractional duration literal,
        # and a malformed one does not come back as a statement with ERR — the
        # whole request fails with HTTP 400, so it would read as a transport
        # problem rather than as the bad value it is.
        latency = payload.pop("latency_ns")
        ts = payload.pop("ts")
        fields = {
            "ts": f"d'{ts}'",
            "latency": f"{latency}ns",
            **{k: _literal(v) for k, v in payload.items()},
        }
        statements = [
            "CREATE tank_access_event SET " + ", ".join(f"{k} = {v}" for k, v in fields.items())
        ]
        try:
            results = await self._execute(statements[0] + " RETURN id;", session.ns, session.db)
            failed = [r for r in results if r.get("status") != "OK"]
            if failed:
                self.drops.drop("write_refused", RuntimeError(str(failed[0].get("result"))[:200]))
                return False
            event_id = results[0]["result"][0]["id"]
        except Exception as exc:  # noqa: BLE001 - see the module docstring
            self.drops.drop("write_failed", exc)
            return False

        if not refs:
            return True
        rows = []
        for ref in refs:
            row = ref.model_dump(exclude_none=True)
            row_ts = row.pop("ts")
            unit = row.pop("unit", None)
            parts = {
                "event": str(event_id),
                "ts": f"d'{row_ts}'",
                **({"unit": unit} if unit else {}),
                **{k: _literal(v) for k, v in row.items()},
            }
            rows.append(
                "CREATE tank_access_ref SET " + ", ".join(f"{k} = {v}" for k, v in parts.items())
            )
        try:
            results = await self._execute(";\n".join(rows) + ";", session.ns, session.db)
            failed = [r for r in results if r.get("status") != "OK"]
            if failed:
                # The event landed and the refs did not. `obs.refs` on the stored
                # event still says what it claimed, so this shows up as the
                # cardinality mismatch it is rather than as a smaller number.
                self.drops.drop("refs_refused", RuntimeError(str(failed[0].get("result"))[:200]))
                return False
        except Exception as exc:  # noqa: BLE001
            self.drops.drop("refs_failed", exc)
            return False
        return True
