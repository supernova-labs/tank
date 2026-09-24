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
