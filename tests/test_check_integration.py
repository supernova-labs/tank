"""Integration suite: `tank check` against a real SurrealDB (TANK_TEST_URL).

Every test gets its own throwaway database inside the ``tank_test`` namespace.
Fixture rule: golden must pass, sabotage must fail with the right code, and
empty/unfilled tables must read VACUOUS — never PASS.
"""

import base64
import json
import os
import sys
import urllib.error
import urllib.request
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent / "fixtures" / "news_mini"))
from ontology import build as build_news

from tank import Attr, Locator, Ontology, StableId, UnitType
from tank.checks import run_check

URL = os.environ.get("TANK_TEST_URL", "http://127.0.0.1:8019")
USER = os.environ.get("TANK_TEST_USER", "root")
PASSWORD = os.environ.get("TANK_TEST_PASS", "root")
NS = "tank_test"
FIXTURES = Path(__file__).parent / "fixtures"


def _server_up() -> bool:
    try:
        urllib.request.urlopen(f"{URL}/version", timeout=2)
        return True
    except (urllib.error.URLError, OSError):
        return False


pytestmark = pytest.mark.skipif(
    not _server_up(), reason=f"SurrealDB test server not reachable at {URL} (TANK_TEST_URL)"
)


def sql(database: str, statements: str, allow_errors: bool = False) -> list:
    auth = base64.b64encode(f"{USER}:{PASSWORD}".encode()).decode()
    request = urllib.request.Request(
        f"{URL}/sql",
        data=statements.encode(),
        headers={
            "Authorization": f"Basic {auth}",
            "Accept": "application/json",
            "surreal-ns": NS,
            "surreal-db": database,
        },
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        results = json.load(response)
    errors = [r for r in results if r.get("status") != "OK"]
    if errors and not allow_errors:
        raise AssertionError(f"seed failed: {errors[:3]}")
    return results


@pytest.fixture
def database():
    name = f"t_{uuid.uuid4().hex[:12]}"
    # ns/db only materialize on a *write*; bootstrap before real DDL so the
    # first seed statement is not swallowed by a NotFound error.
    sql(name, "DEFINE PARAM $bootstrap VALUE 1;", allow_errors=True)
    sql(name, "DEFINE PARAM $bootstrap2 VALUE 1;")
    yield name
    sql(name, f"REMOVE DATABASE IF EXISTS `{name}`;", allow_errors=True)


def seed(database: str, fixture: str) -> None:
    sql(database, (FIXTURES / fixture / "seed.surql").read_text())


async def check(ontology, database):
    return await run_check(
        ontology, url=URL, namespace=NS, database=database, user=USER, password=PASSWORD
    )


def statuses(report, code: str) -> list[str]:
    return [f.status for f in report.findings if f.code == code]


def fail_codes(report) -> set[str]:
    return {f.code for f in report.findings if f.status == "FAIL"}


def minimal_ontology(table: str = "technical_assessment") -> Ontology:
    return Ontology(
        types=[
            UnitType(
                "report",
                table=table,
                id=StableId.of("code"),
                text="body_text",
                locator=Locator(source="code"),
                attrs=[
                    Attr("status", "string", values=["current", "revoked"]),
                    Attr("issued_at", "datetime"),
                ],
            )
        ],
    )


# --------------------------------------------------------------------- minimal


async def test_minimal_golden_passes(database):
    seed(database, "minimal")
    report = await check(minimal_ontology(), database)
    assert fail_codes(report) == set()
    assert "PASS" in statuses(report, "TBL-001")
    assert report.exit_code() == 0


async def test_minimal_sabotage_missing_table(database):
    seed(database, "minimal")
    report = await check(minimal_ontology(table="technical_assessment_v2"), database)
    assert fail_codes(report) == {"TBL-001"}
    finding = next(f for f in report.findings if f.code == "TBL-001")
    assert "does not exist" in finding.message
    assert report.exit_code() == 1


async def test_minimal_schemaless_variant(database):
    # same data, no DDL at all: implicit TYPE ANY table — per-field sampling path
    golden = (FIXTURES / "minimal" / "seed.surql").read_text()
    creates = "\n".join(line for line in golden.splitlines() if line.startswith("CREATE"))
    sql(database, creates)
    report = await check(minimal_ontology(), database)
    assert fail_codes(report) == set()
    assert "PASS" in statuses(report, "FLD-002")  # sampled presence, nothing structural


async def test_minimal_vocabulary_drift_warns(database):
    seed(database, "minimal")
    ontology = Ontology(
        types=[
            UnitType(
                "report",
                table="technical_assessment",
                text="body_text",
                attrs=[Attr("status", "string", values=["current"])],  # narrower than data
            )
        ]
    )
    report = await check(ontology, database)
    assert "WARN" in statuses(report, "ATTR-010")


async def test_vacuous_empty_table(database):
    ddl = "\n".join(
        line
        for line in (FIXTURES / "minimal" / "seed.surql").read_text().splitlines()
        if line.startswith("DEFINE")
    )
    sql(database, ddl)
    report = await check(minimal_ontology(), database)
    assert "VACUOUS" in [f.status for f in report.findings]
    assert report.exit_code() == 0
    assert report.exit_code(strict=True) == 1


# -------------------------------------------------------------------- news_mini


async def test_news_mini_golden_passes(database):
    seed(database, "news_mini")
    report = await check(build_news(), database)
    assert fail_codes(report) == set()
    assert "PASS" in statuses(report, "REL-002")  # TYPE RELATION direction verified
    assert "PASS" in statuses(report, "REL-003")  # field_link typed record<feed>
    assert "PASS" in statuses(report, "VEC-002")
    assert "PASS" in statuses(report, "VEC-003")
    assert "PASS" in statuses(report, "VEC-010")  # sampled dimensions match
    assert "PASS" in statuses(report, "FTS-001")
    assert "PASS" in statuses(report, "REL-004")  # weight field defined on edge
    assert "PASS" in statuses(report, "FRS-001")


async def test_news_mini_dimension_mismatch(database):
    seed(database, "news_mini")
    report = await check(build_news(dim=8), database)
    assert "VEC-002" in fail_codes(report)  # index DIMENSION 4 != declared 8
    assert "VEC-010" in fail_codes(report)  # sampled embeddings are 4-dim


async def test_news_mini_metric_mismatch(database):
    seed(database, "news_mini")
    report = await check(build_news(metric="euclidean"), database)
    assert "VEC-003" in fail_codes(report)


async def test_news_mini_missing_vector_index(database):
    seed(database, "news_mini")
    sql(database, "REMOVE INDEX idx_vec ON TABLE news;")
    report = await check(build_news(), database)
    assert "VEC-001" in fail_codes(report)


async def test_news_mini_no_embeddings_is_vacuous_not_silent(database):
    # rows exist but no row carries an embedding: VEC-010 must say VACUOUS,
    # never stay silent (review finding: embedding job not yet run)
    seed(database, "news_mini")
    sql(database, "UPDATE news SET emb = NONE;")
    report = await check(build_news(), database)
    assert "VACUOUS" in statuses(report, "VEC-010")


async def test_news_mini_wrong_analyzer_declared(database):
    seed(database, "news_mini")
    report = await check(build_news(analyzer="az_missing"), database)
    assert "FTS-002" in fail_codes(report)


async def test_news_mini_missing_edge_table(database):
    seed(database, "news_mini")
    sql(database, "REMOVE TABLE cites;")
    report = await check(build_news(), database)
    assert "REL-001" in fail_codes(report)
    finding = next(f for f in report.findings if f.code == "REL-001")
    assert "does not exist" in finding.message


async def test_implicit_any_edge_warns(database):
    seed(database, "news_mini")
    # replace a typed edge with an implicit RELATE table
    sql(database, "REMOVE TABLE about; RELATE news:n1->about->topic:t1;")
    report = await check(build_news(), database)
    assert "WARN" in statuses(report, "REL-002")
    warn = next(f for f in report.findings if f.code == "REL-002" and f.status == "WARN")
    assert "IN/OUT" in warn.message


async def test_relation_without_in_out_is_not_a_false_pass(database):
    # review finding: TYPE RELATION with no IN/OUT clause must NOT claim that
    # the server enforces direction — it doesn't
    seed(database, "news_mini")
    sql(
        database,
        "REMOVE TABLE about; DEFINE TABLE about TYPE RELATION SCHEMALESS; "
        "RELATE news:n1->about->topic:t1;",
    )
    report = await check(build_news(), database)
    about = [f for f in report.findings if f.code == "REL-002" and f.subject == "relation:about"]
    assert [f.status for f in about] == ["WARN"]
    assert "enforces direction" not in about[0].message


async def test_news_mini_field_link_wrong_field_fails(database):
    seed(database, "news_mini")
    report = await check(build_news(feed_field="source_feed"), database)
    assert "REL-003" in fail_codes(report)


async def test_report_json_serializes(database):
    seed(database, "minimal")
    report = await check(minimal_ontology(), database)
    parsed = json.loads(report.model_dump_json())
    assert parsed["namespace"] == NS
    assert parsed["not_verified"]
