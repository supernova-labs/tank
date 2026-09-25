"""The two bindings, and the frame that carries a call.

The rule that makes namespace-per-tenant work without a registry per tenant:

    the DECLARATION binds at import (`Registry`) and is blind to the tenant;
    the TENANT binds at the call (`Session`) and is blind to the declaration.

If the tenant moved into the `Registry`, the rule dies and you are back to one
registry per tenant. If the declaration moved into a process-global
`tank.use(ontology)`, import order becomes load-bearing and "which declaration
stamped this event" stops being answerable from the code.

Both travel in `ContextVar`s, which is what lets the sink read them without the
consumer's own function signature changing.
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:  # pragma: no cover - typing only
    from tank.access.event import EventSink
    from tank.access.registry import Registry, ToolDescriptor

__all__ = ["CallerKind", "Session", "ToolFrame", "current_frame", "current_session", "session"]

CallerKind = Literal["tool", "migration", "maintenance", "console", "eval", "unknown"]

#: How Python's error classes map onto the closed vocabulary the event stores.
#: `tool` is the catch-all for an exception raised by the consumer's own code:
#: without the split, every environment failure and every skill failure would
#: read as "the ontology failed" in the summary.
#: Ordered most specific to least. The order is the rule, not a detail:
#: `PermissionError` is a subclass of `OSError`, so listing OSError first made
#: `permission` unreachable and collapsed "access was denied" into "the network
#: failed" — two opposite attributions of blame.
_ERROR_CLASSES: tuple[tuple[tuple[type[BaseException], ...], str], ...] = (
    ((PermissionError,), "permission"),
    ((TimeoutError,), "timeout"),
    ((FileNotFoundError,), "not_found"),
    ((ConnectionError,), "connection"),
    ((KeyError, LookupError), "not_found"),
    ((OSError,), "connection"),
)


def classify_error(exc: BaseException) -> str:
    """Map an exception onto the event's closed `error_class` vocabulary.

    Cancellation is checked first and by name. `asyncio.CancelledError` derives
    from `BaseException`, not `Exception`, and it is the most expensive latency
    datapoint there is — a call that was abandoned rather than one that failed.
    """
    import asyncio

    if isinstance(exc, asyncio.CancelledError):
        return "cancelled"
    name = type(exc).__name__.lower()
    if "timeout" in name:
        return "timeout"
    if "auth" in name or "unauthor" in name or "forbidden" in name:
        return "auth"
    if "syntax" in name or "parse" in name:
        return "query_syntax"
    for classes, label in _ERROR_CLASSES:
        if isinstance(exc, classes):
            return label
    return "tool"


def error_type_of(exc: BaseException) -> str:
    """The fully-qualified class name, which is how a missing error_class is
    discovered without shipping a migration."""
    cls = type(exc)
    return f"{cls.__module__}.{cls.__qualname__}"


@dataclass
class Session:
    """The tenant half of the binding, opened per call by the application."""

    registry: Registry
    sink: EventSink
    ns: str
    db: str
    run_id: str
    caller_kind: CallerKind = "tool"
    skill_version: str | None = None
    conversation_id: str | None = None
    message_id: str | None = None
    server_version: str | None = None


@dataclass
class ToolFrame:
    """One tool call. Never shared between calls, and never reused."""

    descriptor: ToolDescriptor
    session: Session
    args_shape: list[dict[str, str]] = field(default_factory=list)
    scope_value: str | None = None
    scope_observed: bool = False
    #: False the moment the call finishes, and set BEFORE the ContextVar is
    #: reset. That ordering is the whole defence against over-attribution: a
    #: fire-and-forget task created inside the tool inherits the context and
    #: would otherwise keep reporting the tool after it returned. Attributing a
    #: query to a tool that did not make it is worse than not attributing it.
    open: bool = True
    elapsed: float = 0.0
    started_at: float = field(default_factory=time.time)
    refs: list[Any] = field(default_factory=list)
    n_refs: int | None = None
    normalize_failed: bool = False
    error: BaseException | None = None

    def record_error(self, exc: BaseException) -> None:
        self.error = exc

    def record_result(self, result: object) -> None:
        """Check the shape against what the tool declared, and MARK when it does
        not match. Never raise: a tool that returned the wrong shape still
        returned, and the caller gets its value untouched."""
        expected = self.descriptor.returns
        if isinstance(result, list) and all(isinstance(r, expected) for r in result):
            self.refs = list(result)
            self.n_refs = len(result)
        else:
            self.normalize_failed = True


_SESSION: ContextVar[Session | None] = ContextVar("tank_session", default=None)
_FRAME: ContextVar[ToolFrame | None] = ContextVar("tank_frame", default=None)


def current_session() -> Session | None:
    return _SESSION.get()


def current_frame() -> ToolFrame | None:
    """The frame of the call in progress, or None.

    A frame that is present but closed is NOT returned as in-frame traffic by
    the caller of this function; see `ToolFrame.open`.
    """
    return _FRAME.get()


@asynccontextmanager
async def session(
    registry: Registry,
    sink: EventSink,
    *,
    ns: str,
    db: str,
    run_id: str,
    caller_kind: CallerKind = "tool",
    skill_version: str | None = None,
    conversation_id: str | None = None,
    message_id: str | None = None,
    server_version: str | None = None,
) -> AsyncIterator[Session]:
    """Open the tenant binding for the duration of a run.

    `run_id`, `conversation_id` and `message_id` are OPAQUE tokens from the
    caller. Tank stores them and never interprets them — conversation state does
    not enter the library.
    """
    current = Session(
        registry=registry,
        sink=sink,
        ns=ns,
        db=db,
        run_id=run_id,
        caller_kind=caller_kind,
        skill_version=skill_version,
        conversation_id=conversation_id,
        message_id=message_id,
        server_version=server_version,
    )
    token = _SESSION.set(current)
    try:
        yield current
    finally:
        _SESSION.reset(token)


def describe_args(bound: Mapping[str, object]) -> list[dict[str, str]]:
    """The SHAPE of the arguments: names and type names, never values.

    Values are only ever stored when the ontology declares a closed vocabulary
    for them and the literal is a member of it — which is why a CPF is
    structurally unstorable rather than filtered out by a rule someone has to
    remember.
    """
    return [{"name": name, "type": type(value).__name__} for name, value in bound.items()]
