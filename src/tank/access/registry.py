"""The registry, the `access_tool` decorator, and the static REG-* checks.

The decorator is the project's fourth level of enforcement, and the only one
that runs at runtime. Its policy is **marked, never silenced**:

  1. It never invents a failure and never invents a success. The tool's
     exception propagates intact.
  2. A failure of the instrument is not a failure of the subject. If the event
     cannot be written, that is swallowed, logged out of band and counted; the
     tool's result propagates.
  3. Absence is always named. No field is left empty without the event saying
     why.

What it does NOT do, each for a reason: it does not swallow exceptions (there
is no `swallow=True`, not even opt-in); it does not normalize an arbitrary
return into references (Tank never wrote the row, so it does not know its id —
the caller builds the `Ref`); it does not validate scope live (it RECORDS
`scope_value`; checking that the filter reached the predicate before ranking is
0.3); it does not retry (that would multiply events per call and make "usage
per tool" ambiguous before `attempt` has a design); and it does not create its
own table (the doctor never writes, not even to its own tables).
"""

from __future__ import annotations

import functools
import hashlib
import inspect
import time
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from tank.access.context import _FRAME as _FRAME_VAR
from tank.access.context import (
    Session,
    ToolFrame,
    classify_error,
    current_frame,
    current_session,
    describe_args,
    error_type_of,
)
from tank.access.event import AccessEvent, AccessRefRow, Observability
from tank.access.types import Candidate, Evidence, Ref
from tank.ontology import Ontology, Violation

__all__ = ["DeclarationError", "Registry", "ToolDescriptor", "Via"]

Via = Literal["gateway", "own"]
Stage = Literal["ref", "candidate", "evidence"]

#: The stage is DERIVED from what the tool declares it returns, never declared
#: twice. `returns=Candidate` and the `-> list[Candidate]` annotation agree by
#: construction, and the runtime checks that the values agree too.
_STAGE: dict[type, Stage] = {Ref: "ref", Candidate: "candidate", Evidence: "evidence"}


class DeclarationError(Exception):
    """Raised at import, carrying EVERY REG-* violation at once.

    Same channel as `OntologyError`: the build breaks with no database
    involved, and the CLI turns it into exit 2. One violation at a time would
    make fixing a registry an iterative game against the compiler.
    """

    def __init__(self, violations: list[Violation]):
        self.violations = violations
        lines = "\n".join(f"  {v}" for v in violations)
        super().__init__(f"tool declaration is invalid ({len(violations)} violation(s)):\n{lines}")


@dataclass(frozen=True)
class ToolDescriptor:
    """What a tool declared about itself. Neutral on purpose.

    This is what an adapter for LangChain or MCP reads — twelve lines, living in
    the consumer's project rather than in this library.
    """

    name: str
    version: str
    returns: type[Ref]
    via: Via
    scope: str | None
    scope_from: str | None
    description: str | None
    signature: inspect.Signature

    @property
    def stage(self) -> Stage:
        return _STAGE[self.returns]

    @property
    def fingerprint(self) -> str:
        """Derived from the DECLARED surface, never from the body.

        A hash of the source fails in both directions: editing only a comment
        moves it, and moving the SQL into a module constant and changing it does
        not. This one moves when the contract moves, which is what makes "same
        version, different fingerprint" mean someone changed the contract
        without bumping.
        """
        surface = "|".join(
            [
                self.name,
                self.version,
                self.stage,
                self.via,
                self.scope or "",
                self.scope_from or "",
                ",".join(
                    f"{p.name}:{p.annotation if p.annotation is not inspect.Parameter.empty else ''}"
                    for p in self.signature.parameters.values()
                ),
            ]
        )
        return hashlib.sha256(surface.encode()).hexdigest()[:12]


class Registry:
    """The binding between one ontology and the tools that access it.

    One object, created by the consumer and imported by name. Not a mutable
    process singleton (`tank.use(...)`), which would make import order
    load-bearing and make "which declaration stamped this event" unanswerable
    from the code; and not an `ontology=` parameter per tool, which would repeat
    the binding at every call site.
    """

    def __init__(self, ontology: Ontology) -> None:
        self.ontology = ontology
        self.ontology_version = f"{ontology.name}@{ontology.version}"
        self.ontology_hash = ontology.fingerprint()[:12]
        self._tools: dict[str, ToolDescriptor] = {}

    # -- declaration -----------------------------------------------------------

    def access_tool(
        self,
        *,
        name: str,
        version: str,
        returns: type[Ref] = Ref,
        via: Via,
        scope: str | None = None,
        scope_from: str | None = None,
        description: str | None = None,
    ) -> Callable[
        [Callable[..., Coroutine[Any, Any, Any]]], Callable[..., Coroutine[Any, Any, Any]]
    ]:
        """Declare a function as an access tool.

        `name` is explicit and required, never derived from `__name__`: it is a
        join key with no backfill, so renaming the function would fragment the
        series, and snake-casing mangles acronyms. It is also the string an
        agent reads, and a badly named marker has already cost 42 of 50
        first-try failures in this project's own ablation.

        `version` is a declared string, never a hash of the source, for the
        reason in `ToolDescriptor.fingerprint`.

        `scope` and `scope_from` are two parameters rather than one: `scope`
        names the KIND of cut, `scope_from` says which argument carries its
        VALUE. Without the second, the event records what cut was claimed and
        never which cut happened.

        `via` has no default because it is what splits a zero into two opposite
        verdicts: a tool with no events that was supposed to go through the
        gateway was never called, and one that runs its own queries is simply
        not observable that way.
        """

        def decorate(
            fn: Callable[..., Coroutine[Any, Any, Any]],
        ) -> Callable[..., Coroutine[Any, Any, Any]]:
            descriptor = self._register(
                fn,
                name=name,
                version=version,
                returns=returns,
                via=via,
                scope=scope,
                scope_from=scope_from,
                description=description,
            )

            @functools.wraps(fn)
            async def wrapper(*args: object, **kwargs: object) -> object:
                session = current_session()
                if session is None:
                    # No session means no tenant and no sink. The call is not
                    # the instrument's business, so it runs untouched.
                    return await fn(*args, **kwargs)

                frame = _open_frame(descriptor, session, args, kwargs)
                token = _FRAME_VAR.set(frame)
                started = time.perf_counter()
                try:
                    result = await fn(*args, **kwargs)
                except BaseException as exc:
                    frame.record_error(exc)
                    raise
                else:
                    frame.record_result(result)
                    return result
                finally:
                    # This order matters. Closing the frame BEFORE resetting the
                    # ContextVar is what kills over-attribution: a task created
                    # inside the tool and outliving it inherits the context, and
                    # would otherwise keep reporting this tool after it returned.
                    frame.open = False
                    frame.elapsed = time.perf_counter() - started
                    _FRAME_VAR.reset(token)
                    await emit(frame)

            return wrapper

        return decorate

    def descriptor(self, name: str) -> ToolDescriptor:
        return self._tools[name]

    def tools(self) -> list[ToolDescriptor]:
        return list(self._tools.values())

    def _register(
        self,
        fn: Callable[..., Any],
        *,
        name: str,
        version: str,
        returns: type[Ref],
        via: Via,
        scope: str | None,
        scope_from: str | None,
        description: str | None,
    ) -> ToolDescriptor:
        violations: list[Violation] = []
        signature = inspect.signature(fn)

        # REG-001 — a tool name is unique within the registry
        if name in self._tools:
            violations.append(Violation(code="REG-001", message=f"duplicate tool name: {name!r}"))

        # REG-002 — `returns` is one of the three boundary stages
        if returns not in _STAGE:
            violations.append(
                Violation(
                    code="REG-002",
                    message=(
                        f"tool {name!r}: returns={returns!r} is not Ref, Candidate or Evidence"
                    ),
                )
            )

        # REG-003 — `scope` names a Scope declared in this ontology
        declared_scopes = {s.name for s in self.ontology.scopes}
        if scope is not None and scope not in declared_scopes:
            violations.append(
                Violation(
                    code="REG-003",
                    message=(
                        f"tool {name!r}: scope={scope!r} is not a declared scope "
                        f"(declared: {sorted(declared_scopes)})"
                    ),
                )
            )

        # REG-004 — version is non-empty
        if not version:
            violations.append(
                Violation(code="REG-004", message=f"tool {name!r}: version must be non-empty")
            )

        # REG-006 — scope_from names a parameter that exists
        if scope_from is not None and scope_from not in signature.parameters:
            violations.append(
                Violation(
                    code="REG-006",
                    message=(
                        f"tool {name!r}: scope_from={scope_from!r} is not a parameter of "
                        f"{fn.__name__}{signature}"
                    ),
                )
            )
        if scope is not None and scope_from is None:
            violations.append(
                Violation(
                    code="REG-006",
                    message=(
                        f"tool {name!r}: scope={scope!r} declared without scope_from — the event "
                        "would record which kind of cut was claimed and never which cut happened"
                    ),
                )
            )

        # REG-007 — the function is a coroutine. Async-first, with no sync path.
        if inspect.isasyncgenfunction(fn):
            violations.append(
                Violation(
                    code="REG-007",
                    message=(
                        f"tool {name!r}: async generators are not supported — the call has no "
                        "single boundary to close, so latency and n_refs would be fiction"
                    ),
                )
            )
        elif not inspect.iscoroutinefunction(fn):
            violations.append(
                Violation(
                    code="REG-007",
                    message=f"tool {name!r}: must be an async function (there is no sync path)",
                )
            )

        if violations:
            raise DeclarationError(violations)

        descriptor = ToolDescriptor(
            name=name,
            version=version,
            returns=returns,
            via=via,
            scope=scope,
            scope_from=scope_from,
            description=description,
            signature=signature,
        )
        self._tools[name] = descriptor
        return descriptor


def _open_frame(
    descriptor: ToolDescriptor,
    session: Session,
    args: tuple[object, ...],
    kwargs: dict[str, object],
) -> ToolFrame:
    """Build the frame for one call.

    A `bind` failure is Python's own TypeError and propagates with no event: the
    call never happened, so recording one would be inventing traffic.
    """
    bound = descriptor.signature.bind(*args, **kwargs)
    bound.apply_defaults()
    frame = ToolFrame(descriptor=descriptor, session=session)
    frame.args_shape = describe_args(bound.arguments)
    if descriptor.scope_from is not None:
        value = bound.arguments.get(descriptor.scope_from)
        if value is not None:
            frame.scope_value = str(value)
            frame.scope_observed = True
    return frame


def _observability(frame: ToolFrame) -> Observability:
    """Name the reason for every absence, one dimension at a time."""
    descriptor = frame.descriptor
    if descriptor.scope is None:
        scope_state = "undeclared"
    elif frame.scope_observed:
        scope_state = "observed"
    else:
        # The tool declared a scope but the argument carrying its value was
        # None. That is an instrumentation defect, and naming it apart from
        # "this tool has no scope" is what makes it fixable.
        scope_state = "unbound"

    if frame.normalize_failed:
        refs_state = "normalize_failed"
    elif frame.n_refs is not None:
        refs_state = "observed"
    else:
        refs_state = "undeclared_stage"

    return Observability(
        scope=scope_state,
        # This slice writes `capture_mode='direct'`, so no plan is read. Not a
        # missing value: a mode that is below the one that reads plans.
        plan="below_mode",
        args="shape_only",
        error_message="observed" if frame.error is not None else "not_applicable",
        skill="reported" if frame.session.skill_version else "not_reported",
        refs=refs_state,
    )


def build_event(frame: ToolFrame) -> tuple[AccessEvent, list[AccessRefRow]]:
    """Turn a finished frame into the rows the tables accept."""
    session = frame.session
    descriptor = frame.descriptor
    ts = datetime.fromtimestamp(frame.started_at, tz=UTC).isoformat().replace("+00:00", "Z")
    error = frame.error

    event = AccessEvent(
        ts=ts,
        latency_ns=int(frame.elapsed * 1_000_000_000),
        tank_version=_tank_version(),
        ontology_version=session.registry.ontology_version,
        ontology_hash=session.registry.ontology_hash,
        run_id=session.run_id,
        sample_rate=1.0,
        capture_mode="direct",
        attribution="in_frame",
        caller_kind=session.caller_kind,
        error_class="none" if error is None else classify_error(error),
        error_type=None if error is None else error_type_of(error),
        # Only the class and the FQN by default. The server's message quotes
        # literals from the query and an ASSERT quotes the offending value, so
        # the raw text is opt-in per tool rather than on by default.
        error_message=None if error is None else f"{type(error).__name__}",
        args_shape=frame.args_shape,
        obs=_observability(frame),
        tool=descriptor.name,
        tool_version=descriptor.version,
        tool_fingerprint=descriptor.fingerprint,
        stage=descriptor.stage if descriptor.stage != "ref" else None,
        n_refs=frame.n_refs,
        scope=descriptor.scope,
        scope_value=frame.scope_value,
        skill_version=session.skill_version,
        conversation_id=session.conversation_id,
        message_id=session.message_id,
        server_version=session.server_version,
    )

    stage = descriptor.stage
    rows: list[AccessRefRow] = []
    if stage in ("candidate", "evidence"):
        for position, ref in enumerate(frame.refs, start=1):
            rows.append(
                AccessRefRow(
                    ts=ts,
                    tool=descriptor.name,
                    unit_type=ref.type,
                    unit_key=ref.id,
                    unit=ref.id if ":" in ref.id else None,
                    stage=stage,
                    rank=getattr(ref, "rank", None) or position,
                    score=getattr(ref, "score", None),
                    unit_version=getattr(ref, "version", None),
                    content_hash=getattr(ref, "content_hash", None),
                )
            )
    return event, rows


async def emit(frame: ToolFrame) -> bool:
    """Write the event. Never raises into the caller.

    Every failure path here ends in a counted drop with a reason, because "no
    events" and "events we failed to write" must never collapse into the same
    zero — one of them means a tool was never called and the other means the
    instrument is broken, and they call for opposite actions.
    """
    session = frame.session
    try:
        event, rows = build_event(frame)
    except Exception as exc:  # noqa: BLE001 - a malformed event is a drop, not a crash
        session.sink.drops.drop("build_failed", exc)
        return False
    try:
        return await session.sink.write(session, event, rows)
    except Exception as exc:  # noqa: BLE001 - see the module docstring
        session.sink.drops.drop("sink_raised", exc)
        return False


def _tank_version() -> str:
    from tank import __version__

    return __version__


def orphan_frame_attribution() -> str:
    """What a query outside any open frame should be attributed to.

    Exposed for the gateway, which is the other half of this and does not exist
    yet. Kept here so the three states stay defined in one place: `in_frame` is
    a live call, `stale` is a frame that outlived its tool, and `none` is
    genuine tool-less traffic that must never be silenced — silencing it would
    erase legitimate tool traffic from a thread that did not inherit context.
    """
    frame = current_frame()
    if frame is None:
        return "none"
    return "in_frame" if frame.open else "stale"
