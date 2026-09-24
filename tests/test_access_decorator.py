"""The decorator, at runtime: what it records, and what it refuses to record.

The policy under test is "marked, never silenced". Three rules, and each one has
a test that fails if the rule is dropped:

  the tool's exception propagates intact, and is classified without being
  altered; a failure of the instrument never becomes a failure of the subject;
  and no field is left empty without the event naming why.

The last one is the one that is easy to fake. A test that only checked "the
event has a scope_value" would pass on an implementation that wrote one
whenever it could and left the field absent otherwise — which is precisely the
encoding this project rejects. So every absence is asserted through `obs.*`,
where the reason lives.
"""

from __future__ import annotations

import asyncio
import threading

import pytest

from tank import Attr, Ontology, Scope, UnitType
from tank.access import (
    Candidate,
    DeclarationError,
    Evidence,
    MemorySink,
    Ref,
    Registry,
    refs_from,
    session,
)


def ontology() -> Ontology:
    return Ontology(
        name="newsroom",
        version="1.0.0",
        types=[
            UnitType("news", table="news", attrs=[Attr("title", "string")]),
            UnitType("entity", table="entity", attrs=[Attr("name", "string")]),
        ],
        scopes=[Scope("entity"), Scope("desk")],
    )


@pytest.fixture
def registry() -> Registry:
    return Registry(ontology())


@pytest.fixture
def sink() -> MemorySink:
    return MemorySink()


def run(registry: Registry, sink: MemorySink, **over):
    kwargs = {"ns": "acme", "db": "tank", "run_id": "conv-7d2f/msg-3", **over}
    return session(registry, sink, **kwargs)


# -------------------------------------------------------------- what it records


async def test_one_call_writes_one_event_and_one_row_per_ref(registry, sink):
    @registry.access_tool(
        name="news_by_entity",
        version="1.0.0",
        returns=Candidate,
        via="own",
        scope="entity",
        scope_from="entity_id",
    )
    async def news_by_entity(entity_id: str, limit: int = 20) -> list[Candidate]:
        return refs_from([{"id": "news:n1"}, {"id": "news:n2"}], type="news", stage=Candidate)

    async with run(registry, sink):
        result = await news_by_entity("entity:e1")

    assert [r.id for r in result] == ["news:n1", "news:n2"]
    assert len(sink.events) == 1
    event = sink.events[0]
    assert event.tool == "news_by_entity"
    assert event.tool_version == "1.0.0"
    assert event.capture_mode == "direct"
    assert event.attribution == "in_frame"
    assert event.error_class == "none"
    assert event.n_refs == 2
    assert event.stage == "candidate"
    assert event.scope == "entity"
    assert event.scope_value == "entity:e1"
    assert event.obs.scope == "observed"
    assert event.obs.refs == "observed"
    assert event.latency_ns >= 0
    assert [(r.unit_key, r.rank) for r in sink.refs] == [("news:n1", 1), ("news:n2", 2)]


async def test_arguments_are_recorded_as_shape_and_never_as_values(registry, sink):
    """The event records that a `cpf` argument existed, never what was in it.

    A value only reaches the database when the ontology declares a closed
    vocabulary for it and the literal is a member — so a national ID is
    structurally unstorable rather than filtered by a rule someone maintains.
    """

    @registry.access_tool(name="lookup", version="1.0.0", via="own")
    async def lookup(cpf: str, limit: int = 10) -> list[Ref]:
        return []

    async with run(registry, sink):
        await lookup("12345678900")

    event = sink.events[0]
    assert event.args_shape == [
        {"name": "cpf", "type": "str"},
        {"name": "limit", "type": "int"},
    ]
    assert event.obs.args == "shape_only"
    assert "12345678900" not in event.model_dump_json()


async def test_the_declaration_stamps_every_event(registry, sink):
    @registry.access_tool(name="t", version="1.0.0", via="own")
    async def t() -> list[Ref]:
        return []

    async with run(registry, sink):
        await t()

    event = sink.events[0]
    assert event.ontology_version == "newsroom@1.0.0"
    assert event.ontology_hash == ontology().fingerprint()[:12]


# ------------------------------------------------ the tool's failure is its own


async def test_the_exception_propagates_intact_and_is_classified(registry, sink):
    """There is no `swallow=True`, not even opt-in. Converting a loud failure
    into a silent empty result is the one thing the decorator must never do."""
    boom = TimeoutError("upstream took too long")

    @registry.access_tool(name="flaky", version="1.0.0", via="own")
    async def flaky() -> list[Ref]:
        raise boom

    with pytest.raises(TimeoutError) as caught:
        async with run(registry, sink):
            await flaky()

    assert caught.value is boom, "the very same exception object, unaltered"
    event = sink.events[0]
    assert event.error_class == "timeout"
    assert event.error_type == "builtins.TimeoutError"
    assert event.obs.error_message == "observed"


async def test_cancellation_is_recorded_and_not_swallowed(registry, sink):
    """`CancelledError` derives from BaseException, so `except Exception` would
    miss it — and an abandoned call is the most expensive latency datapoint
    there is."""

    @registry.access_tool(name="slow", version="1.0.0", via="own")
    async def slow() -> list[Ref]:
        await asyncio.sleep(10)
        return []

    async with run(registry, sink):
        task = asyncio.create_task(slow())
        await asyncio.sleep(0.01)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    assert sink.events[0].error_class == "cancelled"


async def test_a_broken_sink_does_not_break_the_call(registry, sink):
    """A failure of the instrument is not a failure of the subject."""

    class Exploding(MemorySink):
        async def write(self, *a, **k):
            raise RuntimeError("the database is on fire")

    exploding = Exploding()

    @registry.access_tool(name="fine", version="1.0.0", returns=Candidate, via="own")
    async def fine() -> list[Candidate]:
        return [Candidate(type="news", id="news:n1")]

    async with run(registry, exploding):
        result = await fine()

    assert [r.id for r in result] == ["news:n1"], "the tool's result is untouched"
    assert exploding.drops.total == 1
    assert exploding.drops.reasons["sink_raised"] == 1


# --------------------------------------------------------- absence is named


async def test_a_scope_declared_but_not_bound_says_unbound_not_nothing(registry, sink):
    """The difference between `unbound` and `undeclared` is the difference
    between an instrumentation defect and a fact about the product. Collapsing
    them into one absent field loses the only thing that makes one actionable."""

    @registry.access_tool(
        name="by_desk",
        version="1.0.0",
        via="own",
        scope="desk",
        scope_from="desk",
    )
    async def by_desk(desk: str | None = None) -> list[Ref]:
        return []

    async with run(registry, sink):
        await by_desk(desk="science")
        await by_desk()

    bound, unbound = sink.events
    assert (bound.obs.scope, bound.scope_value) == ("observed", "science")
    assert (unbound.obs.scope, unbound.scope_value) == ("unbound", None)


async def test_a_tool_with_no_scope_says_undeclared(registry, sink):
    @registry.access_tool(name="all_news", version="1.0.0", via="own")
    async def all_news() -> list[Ref]:
        return []

    async with run(registry, sink):
        await all_news()

    assert sink.events[0].obs.scope == "undeclared"
    assert sink.events[0].scope_value is None


async def test_a_wrong_return_shape_is_marked_and_never_raised(registry, sink):
    """The tool returned something; the caller gets it. What Tank knows is that
    it could not read references out of it, and it says so rather than
    recording zero refs — which would read as "this tool delivers nothing"."""

    @registry.access_tool(name="sloppy", version="1.0.0", returns=Candidate, via="own")
    async def sloppy():
        return [{"id": "news:n1"}, {"id": "news:n2"}]

    async with run(registry, sink):
        result = await sloppy()

    assert result == [{"id": "news:n1"}, {"id": "news:n2"}], "untouched"
    event = sink.events[0]
    assert event.obs.refs == "normalize_failed"
    assert event.n_refs is None, "not zero — zero would be a claim"
    assert sink.refs == []


async def test_the_plan_dimension_says_below_mode_rather_than_nothing(registry, sink):
    """This slice does not read query plans. That is a mode, not a missing
    value, and the event says which."""

    @registry.access_tool(name="t", version="1.0.0", via="own")
    async def t() -> list[Ref]:
        return []

    async with run(registry, sink):
        await t()

    assert sink.events[0].obs.plan == "below_mode"
    assert sink.events[0].capture_mode == "direct"


async def test_skill_version_has_three_states_not_two(registry, sink):
    """The decorator cannot originate it; only the caller can. So "the caller
    did not report one" is a state of its own."""

    @registry.access_tool(name="t", version="1.0.0", via="own")
    async def t() -> list[Ref]:
        return []

    async with run(registry, sink):
        await t()
    async with run(registry, sink, skill_version="skill@3"):
        await t()

    assert sink.events[0].obs.skill == "not_reported"
    assert sink.events[1].obs.skill == "reported"
    assert sink.events[1].skill_version == "skill@3"


# ------------------------------------------------------------- attribution


async def test_concurrent_tools_do_not_leak_into_each_other(registry, sink):
    @registry.access_tool(name="a", version="1.0.0", via="own")
    async def a() -> list[Ref]:
        await asyncio.sleep(0.01)
        return []

    @registry.access_tool(name="b", version="1.0.0", via="own")
    async def b() -> list[Ref]:
        return []

    async with run(registry, sink):
        await asyncio.gather(a(), b(), a())

    assert sorted(e.tool for e in sink.events) == ["a", "a", "b"]
    assert all(e.attribution == "in_frame" for e in sink.events)


async def test_a_raw_thread_does_not_inherit_the_frame(registry, sink):
    """Measured, and it is half the reason the design looks the way it does.

    A synchronous pool or a legacy ORM running inside a tool does not inherit
    the ContextVar, so its traffic arrives with no tool attached. That bucket is
    never silenced: silencing it would erase legitimate tool traffic, and a tool
    whose queries all come through a raw thread would read as "never called".
    """
    from tank.access.registry import orphan_frame_attribution

    seen: list[str] = []

    @registry.access_tool(name="threaded", version="1.0.0", via="own")
    async def threaded() -> list[Ref]:
        thread = threading.Thread(target=lambda: seen.append(orphan_frame_attribution()))
        thread.start()
        thread.join()
        seen.append(orphan_frame_attribution())
        return []

    async with run(registry, sink):
        await threaded()

    assert seen == ["none", "in_frame"], "the raw thread sees no frame; the coroutine does"


async def test_work_outliving_the_tool_reads_as_stale_not_in_frame(registry, sink):
    """Attributing a query to a tool that did not make it is worse than not
    attributing it. The frame carries an `open` flag, closed BEFORE the
    ContextVar is reset, precisely so that a task which outlives its tool is
    detected instead of credited."""
    from tank.access.registry import orphan_frame_attribution

    seen: list[str] = []
    released = asyncio.Event()

    @registry.access_tool(name="fire_and_forget", version="1.0.0", via="own")
    async def fire_and_forget() -> list[Ref]:
        async def later():
            await released.wait()
            seen.append(orphan_frame_attribution())

        asyncio.create_task(later())
        return []

    async with run(registry, sink):
        await fire_and_forget()
        released.set()
        await asyncio.sleep(0.01)

    assert seen == ["stale"]


async def test_without_a_session_the_call_runs_untouched(registry, sink):
    @registry.access_tool(name="t", version="1.0.0", returns=Candidate, via="own")
    async def t() -> list[Candidate]:
        return [Candidate(type="news", id="news:n1")]

    result = await t()
    assert [r.id for r in result] == ["news:n1"]
    assert sink.events == []


# -------------------------------------------------- REG-*: refused at import


def test_reg001_duplicate_tool_name(registry):
    @registry.access_tool(name="dup", version="1.0.0", via="own")
    async def one() -> list[Ref]:
        return []

    with pytest.raises(DeclarationError) as err:

        @registry.access_tool(name="dup", version="1.0.0", via="own")
        async def two() -> list[Ref]:
            return []

    assert [v.code for v in err.value.violations] == ["REG-001"]


def test_reg003_scope_must_be_declared_in_the_ontology(registry):
    with pytest.raises(DeclarationError) as err:

        @registry.access_tool(name="t", version="1.0.0", via="own", scope="nope", scope_from="x")
        async def t(x: str) -> list[Ref]:
            return []

    assert [v.code for v in err.value.violations] == ["REG-003"]


def test_reg006_scope_without_scope_from_is_refused(registry):
    with pytest.raises(DeclarationError) as err:

        @registry.access_tool(name="t", version="1.0.0", via="own", scope="entity")
        async def t(entity_id: str) -> list[Ref]:
            return []

    assert [v.code for v in err.value.violations] == ["REG-006"]


def test_reg006_scope_from_must_name_a_real_parameter(registry):
    with pytest.raises(DeclarationError) as err:

        @registry.access_tool(
            name="t", version="1.0.0", via="own", scope="entity", scope_from="typo"
        )
        async def t(entity_id: str) -> list[Ref]:
            return []

    assert [v.code for v in err.value.violations] == ["REG-006"]


def test_reg007_a_sync_function_is_refused(registry):
    with pytest.raises(DeclarationError) as err:

        @registry.access_tool(name="t", version="1.0.0", via="own")
        def t() -> list[Ref]:
            return []

    assert [v.code for v in err.value.violations] == ["REG-007"]


def test_reg007_an_async_generator_is_refused(registry):
    """A generator has no single boundary to close, so latency and n_refs would
    be fiction rather than measurement."""
    with pytest.raises(DeclarationError) as err:

        @registry.access_tool(name="t", version="1.0.0", via="own")
        async def t():
            yield Ref(type="news", id="news:n1")

    assert [v.code for v in err.value.violations] == ["REG-007"]


def test_every_violation_is_reported_at_once(registry):
    """One at a time would make fixing a registry a game against the compiler."""
    with pytest.raises(DeclarationError) as err:

        @registry.access_tool(name="t", version="", via="own", scope="nope", scope_from="typo")
        def t(x: str) -> list[Ref]:
            return []

    assert sorted(v.code for v in err.value.violations) == [
        "REG-003",
        "REG-004",
        "REG-006",
        "REG-007",
    ]


# ----------------------------------------------------------- the fingerprint


def test_the_fingerprint_follows_the_declared_surface_not_the_body(registry):
    """Same version with a different fingerprint means someone changed the
    contract without bumping. A hash of the source would fail both ways: a
    comment-only edit would move it, and moving the SQL into a constant and
    changing it would not."""

    @registry.access_tool(name="a", version="1.0.0", via="own")
    async def a(entity_id: str) -> list[Ref]:
        return []  # body one

    other = Registry(ontology())

    @other.access_tool(name="a", version="1.0.0", via="own")
    async def a_again(entity_id: str) -> list[Ref]:
        # A completely different body, same declared surface.
        await asyncio.sleep(0)
        return []

    assert registry.descriptor("a").fingerprint == other.descriptor("a").fingerprint

    third = Registry(ontology())

    @third.access_tool(name="a", version="1.0.0", via="own")
    async def a_wider(entity_id: str, extra: int = 0) -> list[Ref]:
        return []

    assert third.descriptor("a").fingerprint != registry.descriptor("a").fingerprint


def test_the_descriptor_is_neutral_enough_to_build_an_adapter_from(registry):
    """This is what a twelve-line LangChain or MCP adapter reads, and it lives
    in the consumer's project rather than in this library."""

    @registry.access_tool(
        name="search_news",
        version="2.0.0",
        returns=Evidence,
        via="own",
        description="Full-text search over the newsroom.",
    )
    async def search_news(q: str, limit: int = 10) -> list[Evidence]:
        return []

    d = registry.descriptor("search_news")
    assert d.name == "search_news"
    assert d.stage == "evidence"
    assert d.description == "Full-text search over the newsroom."
    assert list(d.signature.parameters) == ["q", "limit"]
