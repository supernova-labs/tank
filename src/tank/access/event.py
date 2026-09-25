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
import math
import time
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
    refs: Literal[
        "observed", "undeclared_stage", "normalize_failed", "errored", "below_mode", "expired"
    ]


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


def _record(ref_id: str) -> str:
    """Render a record id as an expression, without ever concatenating it raw.

    This is the one value in the event that is NOT a literal — it is a record
    pointer, so quoting it would turn it into a string. That exception used to
    be an injection: the id comes from the consumer, the ref rows are sent as a
    multi-statement request, and a `;` inside the id closed the statement and
    ran whatever followed. A single `Ref(id="news:n1; REMOVE TABLE news; --")`
    dropped a table in the consumer's own database, and the drop counter logged
    it as `refs_refused` — the damage done, reported as a benign instrument
    failure.

    `type::record` takes the table and the key as ordinary values, so both go
    through `_literal` and nothing the consumer sends can leave its quotes.
    (The function is `type::record` on 3.x; 2.x spells it `type::thing`, and
    a 2.x adapter would need the other name.)
    """
    table, _, key = ref_id.partition(":")
    return f"type::record({_literal(table)}, {_literal(key)})"


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
        if isinstance(value, float) and not math.isfinite(value):
            # SurrealDB reads `inf`/`nan` as undefined variables and stores
            # NONE, so a score the caller sent would silently become an absence.
            raise ValueError(f"non-finite number cannot be recorded: {value!r}")
        return repr(value)
    if isinstance(value, str):
        # json.dumps gives correct escaping for quotes, backslashes and control
        # characters, and SurrealQL accepts double-quoted strings. Hand-rolled
        # quoting here would be an injection surface in the one place that
        # writes the consumer's own database.
        # ensure_ascii=False: the default emits surrogate pairs for anything
        # outside the BMP, and SurrealDB rejects that escape — an emoji in a
        # run_id would lose the whole event.
        return json.dumps(value, ensure_ascii=False)
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

    #: A tenant that is not ready is re-probed on this schedule rather than
    #: never. A permanent negative meant a tenant provisioned after boot stayed
    #: dark until the process restarted; a permanent positive meant a tenant
    #: re-provisioned under a live process got written to blind, fabricating the
    #: schemaless table the guard exists to prevent. Both were measured.
    RECHECK_AFTER = (30.0, 60.0, 300.0)

    def __init__(self, execute: Any, clock: Any = None) -> None:
        #: async callable (sql, ns, db) -> list of statement results
        self._execute = execute
        self.drops = DropCounter()
        #: (ns, db) -> (ready, checked_at, consecutive failures)
        self._checked: dict[tuple[str, str], tuple[bool, float, int]] = {}
        self._clock = clock or time.monotonic

    def _backoff(self, failures: int) -> float:
        return self.RECHECK_AFTER[min(failures, len(self.RECHECK_AFTER) - 1)]

    async def _table_is_ready(self, session: Session) -> bool:
        """Is this tenant migrated? Cached, but never forever.

        The drop is counted on EVERY refusal, not only the first. Counting it
        once meant five lost events reported as one — and "no events" against
        "events we failed to write" collapsing into the same zero is the thing
        the counter exists to prevent.
        """
        key = (session.ns, session.db)
        now = self._clock()
        cached = self._checked.get(key)
        if cached is not None:
            ready, checked_at, failures = cached
            if ready or now - checked_at < self._backoff(failures):
                if not ready:
                    self.drops.drop("table_missing")
                return ready

        try:
            info = await self._execute("INFO FOR DB;", session.ns, session.db)
            tables = (info[0].get("result") or {}).get("tables", {})
            ddl = tables.get("tank_access_event", "")
            ready = bool(ddl) and "SCHEMAFULL" in ddl
        except Exception as exc:  # noqa: BLE001 - an unreachable database is a drop, not a crash
            self.drops.drop("bootstrap_failed", exc)
            return False

        failures = 0 if ready else (cached[2] + 1 if cached else 0)
        self._checked[key] = (ready, now, failures)
        if not ready:
            self.drops.drop("table_missing")
        return ready

    def forget(self, ns: str, db: str) -> None:
        """Drop what we believe about a tenant, so the next call probes again.

        For the case the backoff cannot see: a tenant re-provisioned while this
        process is alive. The positive answer is cached without expiry on
        purpose — re-probing a healthy tenant on every call would put an
        `INFO FOR DB` on the hot path of every tool call in the system — so a
        re-provision needs to say so.
        """
        self._checked.pop((ns, db), None)

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
        try:
            rows = self._ref_statements(event_id, refs)
        except ValueError as exc:
            # A value the consumer sent cannot be encoded without changing what
            # it means. Its own reason, because "the sink broke" and "this value
            # is not storable" call for different actions.
            self.drops.drop("unencodable_value", exc)
            return False
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

    def _ref_statements(self, event_id: object, refs: list[AccessRefRow]) -> list[str]:
        rows = []
        for ref in refs:
            row = ref.model_dump(exclude_none=True)
            row_ts = row.pop("ts")
            unit = row.pop("unit", None)
            parts = {
                "event": str(event_id),
                "ts": f"d'{row_ts}'",
                **({"unit": _record(unit)} if unit else {}),
                **{k: _literal(v) for k, v in row.items()},
            }
            rows.append(
                "CREATE tank_access_ref SET " + ", ".join(f"{k} = {v}" for k, v in parts.items())
            )
        return rows
