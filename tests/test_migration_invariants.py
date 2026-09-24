"""The access-trail schema, enforced by the database rather than by discipline.

`0001_access.surql` is where the hard requirement stops being a principle and
becomes a constraint: a core field is non-`option`, so an incomplete event is
refused by the server, and every tier-dependent group has a sibling in `obs.*`
whose vocabulary names the reason it is absent.

None of that is worth anything asserted. Every invariant below is checked in
both directions — the event that must be refused AND the neighbouring event
that must be accepted — because a schema that refuses everything passes a
one-sided test just as happily as a correct one.

The fields are not backfillable. Once the first event is written in a tenant,
changing this schema means choosing between inventing states nobody observed
and deleting the series the whole thing exists to produce. So these tests are
the gate, not documentation of it.
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

from tank.introspect import Introspector

URL = os.environ.get("TANK_TEST_URL", "http://127.0.0.1:8019")
USER = os.environ.get("TANK_TEST_USER", "root")
PASSWORD = os.environ.get("TANK_TEST_PASS", "root")
NS = "tank_test_migration"
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


def sql(statements: str, database: str, namespace: str = NS) -> list:
    auth = base64.b64encode(f"{USER}:{PASSWORD}".encode()).decode()
    request = urllib.request.Request(
        f"{URL}/sql",
        data=statements.encode(),
        headers={
            "Authorization": f"Basic {auth}",
            "Accept": "application/json",
            "surreal-ns": namespace,
            "surreal-db": database,
        },
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)


def status(statement: str, database: str) -> str:
    return sql(statement, database)[0].get("status")


@pytest.fixture(scope="module")
def migrated() -> str:
    """A throwaway database with the migration applied.

    The namespace is created explicitly. That is not ceremony: see
    `test_a_missing_namespace_lets_most_of_the_migration_through`.
    """
    name = f"m_{uuid.uuid4().hex[:12]}"
    sql(f"DEFINE NAMESPACE {NS}; USE NS {NS}; DEFINE DATABASE {name};", database="", namespace="")
    results = sql(MIGRATION.read_text(), database=name)
    failed = [r for r in results if r.get("status") != "OK"]
    assert not failed, failed[:3]
    yield name
    sql(f"REMOVE DATABASE IF EXISTS `{name}`;", database=name)


# ------------------------------------------------------------------ the event

# A complete, minimal event: every core field present, every obs dimension in a
# state that claims nothing. Each case below is this, with one thing changed.
BASE = {
    "ts": "d'2026-09-23T10:00:00Z'",
    "latency": "200ms",
    "tank_version": "'0.2.0'",
    "ontology_version": "'acme@1.0.0'",
    "ontology_hash": "'abc123def456'",
    "run_id": "'conv-7d2f/msg-3'",
    "sample_rate": "1.0f",
    "capture_mode": "'direct'",
    "attribution": "'none'",
    "caller_kind": "'tool'",
    "error_class": "'none'",
    "args_shape": "[]",
    "obs": (
        "{scope:'undeclared', plan:'below_mode', args:'shape_only', "
        "error_message:'not_applicable', skill:'not_reported', refs:'below_mode'}"
    ),
}


def obs_with(**changes: str) -> str:
    base = {
        "scope": "'undeclared'",
        "plan": "'below_mode'",
        "args": "'shape_only'",
        "error_message": "'not_applicable'",
        "skill": "'not_reported'",
        "refs": "'below_mode'",
    }
    base.update(changes)
    return "{" + ", ".join(f"{k}:{v}" for k, v in base.items()) + "}"


def write_event(database: str, row_id: str, **overrides: str | None) -> str:
    fields = {**BASE, **overrides}
    assignments = ", ".join(f"{k} = {v}" for k, v in fields.items() if v is not None)
    return status(f"CREATE tank_access_event:{row_id} SET {assignments};", database)


# (label, overrides, expected status). Every "ERR" is paired with the "OK" that
# differs from it by exactly the thing being tested.
CASES: list[tuple[str, dict, str]] = [
    ("a complete minimal event", {}, "OK"),
    # the core is DDL, not discipline
    ("no capture_mode", {"capture_mode": None}, "ERR"),
    ("capture_mode outside the vocabulary", {"capture_mode": "'l3a'"}, "ERR"),
    ("no obs at all", {"obs": None}, "ERR"),
    ("no run_id", {"run_id": None}, "ERR"),
    # sample_rate carries no DEFAULT: a default would assert "this row is one
    # call", and a sampler that forgot to set it would inflate every rate by 1/r
    ("no sample_rate", {"sample_rate": None}, "ERR"),
    # run_id is a string and never a uuid: this value is from the design's own
    # example and uuid rejects it, in a core field with no backfill
    ("run_id with a slash in it", {"run_id": "'conv-7d2f/msg-3'"}, "OK"),
    # the per-tool series is keyed by (tool, tool_version)
    ("tool without tool_version", {"tool": "'search'", "attribution": "'in_frame'"}, "ERR"),
    (
        "tool with tool_version",
        {"tool": "'search'", "tool_version": "'1.0.0'", "attribution": "'in_frame'"},
        "OK",
    ),
    ("attribution in_frame with no tool", {"attribution": "'in_frame'"}, "ERR"),
    ("error_class set, error_type missing", {"error_class": "'timeout'"}, "ERR"),
    (
        "error_class set, error_type present",
        {"error_class": "'timeout'", "error_type": "'builtins.TimeoutError'"},
        "OK",
    ),
    # the mode describes what HAPPENED, and the lie is barred in both directions
    (
        "gateway_plan claiming no plan was observed",
        {"capture_mode": "'gateway_plan'", "obs": obs_with(plan="'disabled'")},
        "ERR",
    ),
    (
        "gateway_plan with a plan observed",
        {"capture_mode": "'gateway_plan'", "obs": obs_with(plan="'observed'")},
        "OK",
    ),
    (
        "direct claiming a plan was observed",
        {"obs": obs_with(plan="'observed'")},
        "ERR",
    ),
    # the five paired asserts: a dimension cannot claim 'observed' over a field
    # that is not there, or the catalog counts that row in the denominator of
    # "we know"
    ("obs.refs observed, n_refs missing", {"obs": obs_with(refs="'observed'")}, "ERR"),
    (
        "obs.refs observed, n_refs present",
        {"n_refs": "7", "obs": obs_with(refs="'observed'")},
        "OK",
    ),
    ("obs.scope observed, scope_value missing", {"obs": obs_with(scope="'observed'")}, "ERR"),
    (
        "obs.scope observed, scope_value present",
        {"scope": "'entity'", "scope_value": "'e:42'", "obs": obs_with(scope="'observed'")},
        "OK",
    ),
    ("obs.args observed, args_values missing", {"obs": obs_with(args="'observed'")}, "ERR"),
    (
        "obs.args observed, args_values present",
        {"args_values": "[{name:'q', value:'x'}]", "obs": obs_with(args="'observed'")},
        "OK",
    ),
    (
        "obs.error_message observed, message missing",
        {"obs": obs_with(error_message="'observed'")},
        "ERR",
    ),
    (
        "obs.error_message observed, message present",
        {"error_message": "'boom'", "obs": obs_with(error_message="'observed'")},
        "OK",
    ),
    ("obs.skill reported, skill_version missing", {"obs": obs_with(skill="'reported'")}, "ERR"),
    (
        "obs.skill reported, skill_version present",
        {"skill_version": "'skill@3'", "obs": obs_with(skill="'reported'")},
        "OK",
    ),
    # SCHEMAFULL is not what defends the core (a non-option field does that even
    # on a SCHEMALESS table); it is what stops an extra column appearing
    ("an undeclared extra field", {"cpf": "'12345678900'"}, "ERR"),
]


@pytest.mark.parametrize(("label", "overrides", "expected"), CASES, ids=[c[0] for c in CASES])
def test_event_invariant(migrated, label, overrides, expected):
    row = f"c{abs(hash(label)) % 10**9}"
    assert write_event(migrated, row, **overrides) == expected


# ------------------------------------------------- what the amendments defend


def test_the_biconditional_survives_the_prune(migrated):
    """An ASSERT on a READONLY field never re-runs, because nothing writes it again.

    `capture_mode` carries the mode/plan biconditional and is READONLY, so it
    guards the CREATE and nothing else. `tank prune` writes `obs.plan`, which
    means that with the assert stated only on `capture_mode`, the prune could
    walk the invariant straight out of the table. Stating it on `obs.plan` too
    is what makes it re-evaluate.
    """
    assert (
        write_event(
            migrated,
            "prune1",
            capture_mode="'gateway_plan'",
            obs=obs_with(plan="'observed'"),
        )
        == "OK"
    )
    broken = "UPDATE tank_access_event:prune1 SET obs.plan = 'disabled';"
    assert status(broken, migrated) == "ERR"
    legitimate = "UPDATE tank_access_event:prune1 SET obs.plan = 'expired';"
    assert status(legitimate, migrated) == "OK"


def test_redaction_writes_a_state_and_never_a_bare_absence(migrated):
    """The prune deletes the value AND records why, or it does not delete at all.

    The assert re-evaluates on a partial UPDATE that does not even touch the
    asserted field, so the database enforces this against `tank prune` itself.
    """
    assert (
        write_event(
            migrated,
            "prune2",
            args_values="[{name:'q', value:'x'}]",
            obs=obs_with(args="'observed'"),
        )
        == "OK"
    )
    assert status("UPDATE tank_access_event:prune2 SET args_values = NONE;", migrated) == "ERR"
    assert (
        status(
            "UPDATE tank_access_event:prune2 SET args_values = NONE, obs.args = 'expired';",
            migrated,
        )
        == "OK"
    )


@pytest.mark.parametrize("field", ["ts", "capture_mode", "ns", "run_id"])
def test_the_event_cannot_be_rewritten(migrated, field):
    assert write_event(migrated, f"ro_{field}") == "OK"
    value = "d'2020-01-01T00:00:00Z'" if field == "ts" else "'rewritten'"
    assert status(f"UPDATE tank_access_event:ro_{field} SET {field} = {value};", migrated) == "ERR"


def test_the_tenant_is_stamped_by_the_server_not_the_client(migrated):
    """With namespace-per-tenant, the easiest field to corrupt is the tenant."""
    assert write_event(migrated, "tenant1", ns="'A_LIE'", db="'A_LIE'") == "OK"
    row = sql("SELECT ns, db FROM tank_access_event:tenant1;", migrated)[0]["result"][0]
    assert row["ns"] == NS
    assert row["db"] == migrated


# --------------------------------------------------------------- the ref rows


def ref(database: str, row_id: str, **overrides: str | None) -> str:
    fields = {
        "event": "tank_access_event:refbase",
        "ts": "d'2026-09-23T10:00:00Z'",
        "unit_type": "'news'",
        "unit_key": "'news:n1'",
        "stage": "'candidate'",
    }
    fields.update(overrides)
    assignments = ", ".join(f"{k} = {v}" for k, v in fields.items() if v is not None)
    return status(f"CREATE tank_access_ref:{row_id} SET {assignments};", database)


def test_unit_key_is_always_written(migrated):
    """D1 said "always", D2 said `option`. Resolved toward always.

    A `unit` link alone is unreadable once its target is deleted, and the
    question `tank_access_ref` exists to answer, which units were never
    accessed, produces a list of deletion candidates. Writing the key as well
    costs ~15 B per row and keeps the answer computable.
    """
    assert write_event(migrated, "refbase") == "OK"
    assert status("CREATE news:n1 SET title = 'x';", migrated) == "OK"
    assert ref(migrated, "nokey", unit="news:n1", unit_key=None) == "ERR"
    assert ref(migrated, "withkey", unit="news:n1") == "OK"


def test_the_proof_of_delivery_outlives_the_unit(migrated):
    """`tank_access_ref` is a normal table and never an edge.

    An edge is deleted in cascade with either endpoint, so the day a consumer
    deletes a document would delete the proof that it was delivered, rewriting
    the usage metric retroactively.
    """
    assert write_event(migrated, "refbase2") == "OK"
    assert status("CREATE news:n2 SET title = 'y';", migrated) == "OK"
    assert ref(migrated, "survivor", event="tank_access_event:refbase2", unit="news:n2") == "OK"
    assert status("DELETE news:n2;", migrated) == "OK"
    row = sql("SELECT unit_key, unit.id AS target FROM tank_access_ref:survivor;", migrated)[0]
    assert row["result"][0] == {"unit_key": "news:n1", "target": None}


# ---------------------------------------------------- the schema, and the ns


async def test_the_schema_passes_the_frameworks_own_parser(migrated):
    """Rule R5: the framework's table passes the framework's validator.

    Zero `FLEXIBLE`, because `parse_field_ddl` mis-parses the postfix spelling
    into a type that matches nothing. That bug is fixed, but a schema that needs
    the fix to be readable is a schema with a dependency it does not need.
    """
    async with Introspector(
        URL, namespace=NS, database=migrated, user=USER, password=PASSWORD
    ) as db:
        info = await db.db_info()
        ours = [t for t in info.tables if t.startswith("tank_")]
        assert len(ours) == 5
        for table in ours:
            table_info = await db.table_info(table)
            unparsed = [n for n, f in table_info.fields.items() if not f.type]
            assert unparsed == [], f"{table}: {unparsed}"
            assert "FLEXIBLE" not in info.tables[table].raw


def test_a_missing_namespace_lets_most_of_the_migration_through(migrated):
    """Why `tank migrate` must validate the namespace before the first statement.

    HTTP headers defend against a namespace typo for `CREATE`, `SELECT` and
    `DEFINE TABLE`, but NOT for `DEFINE FIELD`, which is what a migration is
    mostly made of. So the first statement is refused, the second one creates
    the namespace, the database and its own table, and everything after it
    lands in a tenant that did not exist a moment ago.

    What makes it worse rather than better: only the FIRST table, the ledger,
    is left malformed (`SCHEMALESS`, because its `DEFINE TABLE` was the
    statement that failed). The other four are created normally by their own
    `DEFINE TABLE`, once the namespace exists. A quick `INFO FOR DB` on the
    phantom tenant therefore looks almost right, and the one table that is
    broken is the one that records which migrations were applied.

    This is why `tank migrate` validates the namespace before the first
    statement, and why that is the only defence rather than a redundant one.
    """
    ghost = f"ghost_{uuid.uuid4().hex[:8]}"
    results = sql(MIGRATION.read_text(), database="phantom", namespace=ghost)
    failed = [r for r in results if r.get("status") != "OK"]
    assert len(failed) == 1, "expected exactly the first DEFINE TABLE to be refused"
    assert len(results) - len(failed) > 100, "the rest went through, which is the point"

    tables = sql("INFO FOR DB;", database="phantom", namespace=ghost)[0]["result"]["tables"]
    assert set(tables) == {
        "tank_migration",
        "tank_access_event",
        "tank_access_plan",
        "tank_access_ref",
        "tank_access_rollup",
    }, "a namespace that did not exist now holds the whole schema"
    assert "SCHEMALESS" in tables["tank_migration"], "the ledger is the one left malformed"
    assert all("SCHEMAFULL" in ddl for name, ddl in tables.items() if name != "tank_migration"), (
        "and the rest look fine, which is what makes this hard to notice"
    )
    sql(f"REMOVE NAMESPACE IF EXISTS {ghost};", database="", namespace="")


# --------------------------------- what the database can and cannot enforce


def test_an_assert_on_a_readonly_field_never_re_runs(migrated):
    """The additivity rule A6 depends on this, and it is easy to get backwards.

    A READONLY field is skipped whole on UPDATE — type and assert alike — so an
    assert added to one later is free, and never fires on old rows. A writable
    field is re-validated on every UPDATE, touched or not. Since `tank prune`
    writes `obs.*`, `error_message`, `scope_value` and `args_values`, those are
    exactly the fields where a later assert can break the prune over the whole
    historical series.
    """
    sql(
        "DEFINE TABLE a6 SCHEMAFULL;"
        "DEFINE FIELD ro ON a6 TYPE int READONLY;"
        "DEFINE FIELD rw ON a6 TYPE int;"
        "CREATE a6:1 SET ro = 5, rw = 1;",
        migrated,
    )
    sql("DEFINE FIELD OVERWRITE ro ON a6 TYPE int READONLY ASSERT $value > 100;", migrated)
    assert status("UPDATE a6:1 SET rw = 2;", migrated) == "OK", "READONLY: not re-evaluated"

    sql("DEFINE FIELD OVERWRITE rw ON a6 TYPE int ASSERT $value > 100;", migrated)
    assert status("UPDATE a6:1 SET ro = 5;", migrated) == "ERR", "writable: re-evaluated"


def test_the_obs_asserts_are_in_row_and_cannot_see_the_other_tables(migrated):
    """`obs.refs` holds against `n_refs`, not against the rows in
    `tank_access_ref`. Purging the refs and leaving `obs.refs = 'observed'` is
    therefore accepted — the database cannot enforce it, because an ASSERT only
    sees `$this`. Marking it 'expired' is a convention `tank prune` has to keep,
    and this test exists so nobody mistakes it for a guarantee.
    """
    assert write_event(migrated, "xtab", n_refs="3", obs=obs_with(refs="'observed'")) == "OK"
    assert (
        status(
            "CREATE tank_access_ref:x1 SET event = tank_access_event:xtab, "
            "ts = d'2026-09-23T10:00:00Z', unit_type = 'news', unit_key = 'news:n1', "
            "stage = 'candidate';",
            migrated,
        )
        == "OK"
    )
    assert status("DELETE tank_access_ref:x1;", migrated) == "OK"
    # The event still claims three refs, and the database has no objection.
    assert status("UPDATE tank_access_event:xtab SET obs.refs = 'observed';", migrated) == "OK"
    row = sql("SELECT n_refs, obs.refs AS refs FROM tank_access_event:xtab;", migrated)[0]["result"]
    assert row[0] == {"n_refs": 3, "refs": "observed"}


def test_applying_a_modified_migration_is_swallowed_in_silence(migrated):
    """`IF NOT EXISTS` makes re-application a clean no-op — including when the
    file has CHANGED. The database says 0001 and the file says something else,
    and the checksum in `tank_migration` is the only thing that could ever tell.
    Which is why this file does not write that row: it cannot know its own hash,
    so `tank migrate` has to.
    """
    modified = MIGRATION.read_text().replace(
        "DEFINE FIELD IF NOT EXISTS run_id          ON tank_access_event TYPE string READONLY;",
        "DEFINE FIELD IF NOT EXISTS run_id          ON tank_access_event TYPE uuid READONLY;",
    )
    assert modified != MIGRATION.read_text(), "the replacement has to bite"
    results = sql(modified, migrated)
    assert [r for r in results if r.get("status") != "OK"] == [], "no error at all"

    info = sql("INFO FOR TABLE tank_access_event;", migrated)[0]["result"]
    assert "TYPE string" in info["fields"]["run_id"], "and no effect either"
    ledger = sql("SELECT count() FROM tank_migration GROUP ALL;", migrated)[0]["result"]
    assert ledger[0]["count"] == 0, "the ledger that would catch it is empty"
