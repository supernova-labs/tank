"""The decorator writing into a real database, through the real schema.

The unit tests hold the decorator to its policy. This file holds it to the DDL,
which is a different and harder thing: the core columns are non-`option` with
no backfill, so an event this code builds wrong is refused by the server rather
than stored wrong. Anything here that passes has been through
`0001_access.surql`'s twelve asserts.

It also covers the failure the sink exists to prevent. A `CREATE` against a
table that does not exist SUCCEEDS on SurrealDB and fabricates a
`TYPE ANY SCHEMALESS` table — so on an un-migrated tenant the first event would
invent a schema with none of the invariants, and the core would evaporate on
that very first write.
"""

from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.request
import uuid
from pathlib import Path

import pytest

from tank import Attr, Ontology, Scope, UnitType
from tank.access import Candidate, Registry, SurrealSink, refs_from, session

URL = os.environ.get("TANK_TEST_URL", "http://127.0.0.1:8019")
USER = os.environ.get("TANK_TEST_USER", "root")
PASSWORD = os.environ.get("TANK_TEST_PASS", "root")
NS = "tank_test_access"
MIGRATION = Path(__file__).parent.parent / "src" / "tank" / "migrations" / "0001_access.surql"


def _server_up() -> bool:
    try:
        urllib.request.urlopen(f"{URL}/version", timeout=2)
        return True
    except (urllib.error.URLError, OSError):
        return False


pytestmark = pytest.mark.skipif(
    not _server_up(), reason=f"SurrealDB test server not reachable at {URL} (TANK_TEST_URL)"
)


async def execute(sql: str, ns: str, db: str) -> list:
    """The one connection the sink is given. Deliberately the caller's own: the
    trail is written into the same (ns, db) the data lives in, because a ref to
    a unit in another database is a dangling pointer that no query can check."""
    auth = base64.b64encode(f"{USER}:{PASSWORD}".encode()).decode()
    request = urllib.request.Request(
        f"{URL}/sql",
        data=sql.encode(),
        headers={
            "Authorization": f"Basic {auth}",
            "Accept": "application/json",
            "surreal-ns": ns,
            "surreal-db": db,
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: ASYNC210
        # Blocking on purpose: this stands in for the consumer's own connection,
        # and the point of the test is the shape of that contract, not its
        # concurrency. A real adapter wraps an async driver.
        return json.load(response)


def sync_sql(sql: str, ns: str, db: str) -> list:
    auth = base64.b64encode(f"{USER}:{PASSWORD}".encode()).decode()
    request = urllib.request.Request(
        f"{URL}/sql",
        data=sql.encode(),
        headers={
            "Authorization": f"Basic {auth}",
            "Accept": "application/json",
            "surreal-ns": ns,
            "surreal-db": db,
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def ontology() -> Ontology:
    return Ontology(
        name="newsroom",
        version="1.0.0",
        types=[UnitType("news", table="news", attrs=[Attr("title", "string")])],
        scopes=[Scope("entity")],
    )


@pytest.fixture
def migrated() -> str:
    name = f"a_{uuid.uuid4().hex[:12]}"
    sync_sql(f"DEFINE NAMESPACE {NS}; USE NS {NS}; DEFINE DATABASE {name};", "", "")
    failed = [r for r in sync_sql(MIGRATION.read_text(), NS, name) if r.get("status") != "OK"]
    assert not failed, failed[:2]
    sync_sql("CREATE news:n1 SET title = 'one'; CREATE news:n2 SET title = 'two';", NS, name)
    yield name
    sync_sql(f"REMOVE DATABASE IF EXISTS `{name}`;", NS, name)


@pytest.fixture
def unmigrated() -> str:
    name = f"u_{uuid.uuid4().hex[:12]}"
    sync_sql(f"DEFINE NAMESPACE {NS}; USE NS {NS}; DEFINE DATABASE {name};", "", "")
    yield name
    sync_sql(f"REMOVE DATABASE IF EXISTS `{name}`;", NS, name)


async def test_a_tool_call_lands_in_the_real_tables(migrated):
    """The whole path, through every assert in the schema."""
    registry = Registry(ontology())
    sink = SurrealSink(execute)

    @registry.access_tool(
        name="news_by_entity",
        version="1.0.0",
        returns=Candidate,
        via="own",
        scope="entity",
        scope_from="entity_id",
    )
    async def news_by_entity(entity_id: str, limit: int = 20) -> list[Candidate]:
        rows = await execute("SELECT id FROM news ORDER BY id;", NS, migrated)
        return refs_from(rows[0]["result"], type="news", stage=Candidate)

    async with session(registry, sink, ns=NS, db=migrated, run_id="conv-7d2f/msg-3"):
        result = await news_by_entity("entity:e1")

    assert len(result) == 2
    assert sink.drops.total == 0, sink.drops.reasons

    stored = sync_sql("SELECT * FROM tank_access_event;", NS, migrated)[0]["result"]
    assert len(stored) == 1
    event = stored[0]
    assert event["tool"] == "news_by_entity"
    assert event["capture_mode"] == "direct"
    assert event["attribution"] == "in_frame"
    assert event["n_refs"] == 2
    assert event["scope_value"] == "entity:e1"
    assert event["obs"]["refs"] == "observed"
    assert event["obs"]["plan"] == "below_mode"
    assert event["run_id"] == "conv-7d2f/msg-3"
    # Stamped by the server, not by this code.
    assert event["ns"] == NS
    assert event["db"] == migrated
    assert event["written_at"] >= event["ts"]

    refs = sync_sql("SELECT * FROM tank_access_ref ORDER BY rank;", NS, migrated)[0]["result"]
    assert [(r["unit_key"], r["rank"], r["stage"]) for r in refs] == [
        ("news:n1", 1, "candidate"),
        ("news:n2", 2, "candidate"),
    ]
    assert all(r["event"] == event["id"] for r in refs)


async def test_an_error_lands_with_its_class_and_type(migrated):
    registry = Registry(ontology())
    sink = SurrealSink(execute)

    @registry.access_tool(name="flaky", version="1.0.0", via="own")
    async def flaky() -> list[Candidate]:
        raise TimeoutError("upstream")

    with pytest.raises(TimeoutError):
        async with session(registry, sink, ns=NS, db=migrated, run_id="r1"):
            await flaky()

    event = sync_sql("SELECT * FROM tank_access_event;", NS, migrated)[0]["result"][0]
    assert event["error_class"] == "timeout"
    assert event["error_type"] == "builtins.TimeoutError"
    assert event["obs"]["error_message"] == "observed"
    # The raw server message is NOT stored by default: it quotes literals from
    # the query, and an ASSERT quotes the offending value.
    assert "upstream" not in json.dumps(event)


async def test_the_sink_refuses_to_write_into_an_unmigrated_tenant(unmigrated):
    """This is the guard's whole reason for existing.

    Without it, the first event on an un-migrated tenant would succeed and
    fabricate a `TYPE ANY SCHEMALESS` table — no asserts, no indexes, and a core
    that has no backfill silently gone.
    """
    registry = Registry(ontology())
    sink = SurrealSink(execute)

    @registry.access_tool(name="t", version="1.0.0", returns=Candidate, via="own")
    async def t() -> list[Candidate]:
        return [Candidate(type="news", id="news:n1")]

    async with session(registry, sink, ns=NS, db=unmigrated, run_id="r1"):
        result = await t()

    assert [r.id for r in result] == ["news:n1"], "the call is untouched"
    assert sink.drops.reasons["table_missing"] == 1, "and the refusal is counted, with a reason"

    tables = sync_sql("INFO FOR DB;", NS, unmigrated)[0]["result"]["tables"]
    assert "tank_access_event" not in tables, "nothing was fabricated"


async def test_the_counterfactual_a_blind_write_would_have_fabricated_the_table(unmigrated):
    """The negative case for the test above: without the guard, this is what
    happens. If this ever starts failing, SurrealDB changed and the guard's
    justification needs rereading — not the guard removed."""
    result = sync_sql("CREATE tank_access_event SET tool = 'ghost';", NS, unmigrated)
    assert result[0]["status"] == "OK", "a blind CREATE succeeds"
    ddl = sync_sql("INFO FOR DB;", NS, unmigrated)[0]["result"]["tables"]["tank_access_event"]
    assert "SCHEMALESS" in ddl, "and the table it invents has none of the invariants"


async def test_the_guard_is_checked_once_per_tenant_not_once_per_call(migrated):
    """A lookup per call would put an INFO FOR DB on the hot path of every tool
    call in the system."""
    registry = Registry(ontology())
    sink = SurrealSink(execute)

    @registry.access_tool(name="t", version="1.0.0", via="own")
    async def t() -> list[Candidate]:
        return []

    async with session(registry, sink, ns=NS, db=migrated, run_id="r1"):
        for _ in range(3):
            await t()

    assert list(sink._checked) == [(NS, migrated)]
    assert (
        sync_sql("SELECT count() FROM tank_access_event GROUP ALL;", NS, migrated)[0]["result"][0][
            "count"
        ]
        == 3
    )


async def test_a_wrong_shape_stores_normalize_failed_rather_than_zero_refs(migrated):
    """Zero would be a claim: "this tool delivered nothing". `normalize_failed`
    is the truth: "Tank could not read references out of what it returned"."""
    registry = Registry(ontology())
    sink = SurrealSink(execute)

    @registry.access_tool(name="sloppy", version="1.0.0", returns=Candidate, via="own")
    async def sloppy():
        return [{"id": "news:n1"}]

    async with session(registry, sink, ns=NS, db=migrated, run_id="r1"):
        await sloppy()

    event = sync_sql("SELECT * FROM tank_access_event;", NS, migrated)[0]["result"][0]
    assert event["obs"]["refs"] == "normalize_failed"
    assert "n_refs" not in event or event["n_refs"] is None
    refs = sync_sql("SELECT count() FROM tank_access_ref GROUP ALL;", NS, migrated)[0]["result"]
    assert refs[0]["count"] == 0


async def test_the_trail_answers_the_question_it_exists_for(migrated):
    """End to end: which units were delivered, and which never were."""
    registry = Registry(ontology())
    sink = SurrealSink(execute)

    @registry.access_tool(name="top_news", version="1.0.0", returns=Candidate, via="own")
    async def top_news() -> list[Candidate]:
        return [Candidate(type="news", id="news:n1")]

    async with session(registry, sink, ns=NS, db=migrated, run_id="r1"):
        await top_news()

    delivered = {
        r["unit_key"]
        for r in sync_sql("SELECT unit_key FROM tank_access_ref GROUP BY unit_key;", NS, migrated)[
            0
        ]["result"]
    }
    everything = {str(r["id"]) for r in sync_sql("SELECT id FROM news;", NS, migrated)[0]["result"]}
    assert delivered == {"news:n1"}
    assert everything - delivered == {"news:n2"}


# ------------------------------------------- the one place that writes SQL


HOSTILE_IDS = [
    ("statement terminator", "news:n1; REMOVE TABLE news; --"),
    ("create a table", "news:n1; CREATE pwned:x SET owned = true; --"),
    ("tamper with the trail", 'news:n1; UPDATE tank_access_event SET scope_value = "X"; --'),
    ("exfiltrate", "news:n1; CREATE leak CONTENT (SELECT * FROM news)[0]; --"),
    ("no drop counted", "news:n1 RETURN 1; CREATE pwned2 SET ok = true RETURN 1; --"),
    ("backtick", "news:`a`b`"),
    ("comment opener", "https://example.com/a"),
    ("extra colons", "a:b:c"),
    ("emoji", "news:🎉"),
]


@pytest.mark.parametrize(("label", "hostile"), HOSTILE_IDS, ids=[c[0] for c in HOSTILE_IDS])
async def test_a_reference_id_cannot_run_sql(migrated, label, hostile):
    """`Ref.id` is a record POINTER, so it cannot be quoted like a literal —
    and that exception used to be an injection.

    The ref rows go out as one multi-statement request, so a `;` inside an id
    closed the statement and ran what followed. `Ref(id="news:n1; REMOVE TABLE
    news; --")` dropped a table in the consumer's own database, and the drop
    counter logged `refs_refused`: the damage done, reported as a benign
    instrument failure.

    `type::record(table, key)` takes both halves as ordinary values, so they go
    through the same quoting as everything else.
    """
    registry = Registry(ontology())
    sink = SurrealSink(execute)

    @registry.access_tool(name="t", version="1.0.0", returns=Candidate, via="own")
    async def t() -> list[Candidate]:
        return [Candidate(type="news", id=hostile)]

    before = set(sync_sql("INFO FOR DB;", NS, migrated)[0]["result"]["tables"])
    async with session(registry, sink, ns=NS, db=migrated, run_id="r1"):
        await t()
    after = set(sync_sql("INFO FOR DB;", NS, migrated)[0]["result"]["tables"])

    assert after == before, f"{label} created or removed a table: {after ^ before}"
    assert "news" in after, "the consumer's own table survived"
    assert not sync_sql("SELECT * FROM tank_access_event WHERE scope_value = 'X';", NS, migrated)[
        0
    ]["result"], "the trail was not rewritten"
    # And it is not merely refused: the id is stored, verbatim, as a value.
    assert sink.drops.total == 0, dict(sink.drops.reasons)
    stored = sync_sql("SELECT unit_key FROM tank_access_ref;", NS, migrated)[0]["result"]
    assert [r["unit_key"] for r in stored] == [hostile]


async def test_a_non_finite_score_is_refused_rather_than_stored_as_absence(migrated):
    """SurrealDB reads `inf` and `nan` as undefined variables and stores NONE, so
    a score from a scorer that divided by zero would become indistinguishable
    from a tool that does not score at all."""
    registry = Registry(ontology())
    sink = SurrealSink(execute)

    @registry.access_tool(name="t", version="1.0.0", returns=Candidate, via="own")
    async def t() -> list[Candidate]:
        return [Candidate(type="news", id="news:n1", score=float("inf"))]

    async with session(registry, sink, ns=NS, db=migrated, run_id="r1"):
        await t()

    assert sink.drops.reasons["unencodable_value"] == 1
    rows = sync_sql("SELECT count() FROM tank_access_ref GROUP ALL;", NS, migrated)[0]["result"]
    assert rows[0]["count"] == 0, "refused, rather than stored as a silent None"


# ----------------------------------------- the guard that must not go blind


async def test_every_refusal_is_counted_not_only_the_first(unmigrated):
    """One drop for five lost events is the silent zero the counter exists to
    prevent. Counting only the first refusal meant "no events" and "events we
    failed to write" collapsed into the same number again, one layer down."""
    registry = Registry(ontology())
    sink = SurrealSink(execute)

    @registry.access_tool(name="t", version="1.0.0", returns=Candidate, via="own")
    async def t() -> list[Candidate]:
        return [Candidate(type="news", id="news:n1")]

    async with session(registry, sink, ns=NS, db=unmigrated, run_id="r1"):
        for _ in range(5):
            await t()

    assert sink.drops.reasons["table_missing"] == 5


async def test_a_tenant_migrated_later_is_picked_up(unmigrated):
    """A permanent negative meant a tenant provisioned after boot stayed dark
    until the process restarted — silently, since the drop had stopped being
    counted too."""
    registry = Registry(ontology())
    clock = [0.0]
    sink = SurrealSink(execute, clock=lambda: clock[0])

    @registry.access_tool(name="t", version="1.0.0", returns=Candidate, via="own")
    async def t() -> list[Candidate]:
        return [Candidate(type="news", id="news:n1")]

    async with session(registry, sink, ns=NS, db=unmigrated, run_id="r1"):
        await t()
        assert sink.drops.reasons["table_missing"] == 1

        # Migrate while the process stays alive, then let the backoff elapse.
        failed = [
            r for r in sync_sql(MIGRATION.read_text(), NS, unmigrated) if r.get("status") != "OK"
        ]
        assert not failed
        clock[0] += SurrealSink.RECHECK_AFTER[0] + 1
        await t()

    stored = sync_sql("SELECT count() FROM tank_access_event GROUP ALL;", NS, unmigrated)[0][
        "result"
    ]
    assert stored[0]["count"] == 1, "the second call landed"


async def test_the_probe_is_not_repeated_on_every_call_while_it_is_failing(unmigrated):
    """The backoff has to hold in both directions: re-probing a broken tenant
    on every call would put an `INFO FOR DB` on the hot path of a system that
    is already in trouble."""
    registry = Registry(ontology())
    clock = [0.0]
    probes = []

    async def counting_execute(statements: str, ns: str, db: str) -> list:
        if statements.startswith("INFO FOR DB"):
            probes.append(clock[0])
        return await execute(statements, ns, db)

    sink = SurrealSink(counting_execute, clock=lambda: clock[0])

    @registry.access_tool(name="t", version="1.0.0", via="own")
    async def t() -> list[Candidate]:
        return []

    async with session(registry, sink, ns=NS, db=unmigrated, run_id="r1"):
        for _ in range(4):
            await t()

    assert len(probes) == 1, "one probe for four calls"
    assert sink.drops.reasons["table_missing"] == 4, "but every refusal counted"


async def test_forget_lets_a_reprovisioned_tenant_be_re_probed(migrated):
    """The positive answer is cached without expiry on purpose — re-probing a
    healthy tenant every call would cost an `INFO FOR DB` per tool call. So a
    tenant re-provisioned under a live process has to say so, and until it does
    the sink writes blind and fabricates exactly the schemaless table the guard
    exists to prevent."""
    registry = Registry(ontology())
    sink = SurrealSink(execute)

    @registry.access_tool(name="t", version="1.0.0", via="own")
    async def t() -> list[Candidate]:
        return []

    async with session(registry, sink, ns=NS, db=migrated, run_id="r1"):
        await t()
        assert (NS, migrated) in sink._checked

        sink.forget(NS, migrated)
        assert (NS, migrated) not in sink._checked
        await t()

    assert sink.drops.total == 0
    stored = sync_sql("SELECT count() FROM tank_access_event GROUP ALL;", NS, migrated)[0]["result"]
    assert stored[0]["count"] == 2
