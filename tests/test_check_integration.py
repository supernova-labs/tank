"""Integration suite: `tank check` against a real SurrealDB (TANK_TEST_URL).

Every test gets its own throwaway database inside the ``tank_test`` namespace.
Fixture rule (D1): golden must pass, sabotage must fail with the right code,
and empty tables must read VACUOUS — never PASS.
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

sys.path.insert(0, str(Path(__file__).parent / "fixtures" / "noticias_mini"))
from ontology import build as build_noticias

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
    # A12: ns/db only materialize on a *write*; bootstrap before real DDL so the
    # first seed statement is not swallowed by the NotFound error.
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


def degrau1_ontology(table: str = "parecer_tecnico") -> Ontology:
    return Ontology(
        types=[
            UnitType(
                "laudo",
                table=table,
                id=StableId.of("codigo"),
                text="corpo_texto",
                locator=Locator(source="codigo"),
                attrs=[
                    Attr("situacao", "string", values=["vigente", "revogado"]),
                    Attr("emitido_em", "datetime"),
                ],
            )
        ],
    )


# ------------------------------------------------------------------- degrau 1


async def test_degrau1_golden_passes(database):
    seed(database, "degrau1")
    report = await check(degrau1_ontology(), database)
    assert fail_codes(report) == set()
    assert "PASS" in statuses(report, "TBL-001")
    assert report.exit_code() == 0


async def test_degrau1_sabotage_missing_table(database):
    seed(database, "degrau1")
    report = await check(degrau1_ontology(table="parecer_tecnico_v2"), database)
    assert fail_codes(report) == {"TBL-001"}
    finding = next(f for f in report.findings if f.code == "TBL-001")
    assert "does not exist" in finding.message
    assert report.exit_code() == 1


async def test_degrau1_schemaless_variant(database):
    # same data, no DDL at all: implicit TYPE ANY table — per-field sampling path
    golden = (FIXTURES / "degrau1" / "seed.surql").read_text()
    creates = "\n".join(line for line in golden.splitlines() if line.startswith("CREATE"))
    sql(database, creates)
    report = await check(degrau1_ontology(), database)
    assert fail_codes(report) == set()
    assert "PASS" in statuses(report, "FLD-002")  # sampled presence, nothing structural


async def test_degrau1_vocabulary_drift_warns(database):
    seed(database, "degrau1")
    sql(database, "UPDATE parecer_tecnico:pt001 SET situacao = 'vigente';")
    ontology = Ontology(
        types=[
            UnitType(
                "laudo",
                table="parecer_tecnico",
                text="corpo_texto",
                attrs=[Attr("situacao", "string", values=["vigente"])],  # narrower than data
            )
        ]
    )
    report = await check(ontology, database)
    assert "WARN" in statuses(report, "ATTR-010")


async def test_vacuous_empty_table(database):
    ddl = "\n".join(
        line
        for line in (FIXTURES / "degrau1" / "seed.surql").read_text().splitlines()
        if line.startswith("DEFINE")
    )
    sql(database, ddl)
    report = await check(degrau1_ontology(), database)
    assert "VACUOUS" in [f.status for f in report.findings]
    assert report.exit_code() == 0
    assert report.exit_code(strict=True) == 1


# ------------------------------------------------------------------- noticias_mini


async def test_noticias_mini_golden_passes(database):
    seed(database, "noticias_mini")
    report = await check(build_noticias(), database)
    assert fail_codes(report) == set()
    assert "PASS" in statuses(report, "REL-002")  # TYPE RELATION direction verified
    assert "PASS" in statuses(report, "VEC-002")
    assert "PASS" in statuses(report, "VEC-003")
    assert "PASS" in statuses(report, "VEC-010")  # sampled dimensions match
    assert "PASS" in statuses(report, "FTS-001")
    assert "PASS" in statuses(report, "REL-004")  # weight field defined on edge
    assert "PASS" in statuses(report, "FRS-001")


async def test_noticias_mini_dimension_mismatch(database):
    seed(database, "noticias_mini")
    report = await check(build_noticias(dim=8), database)
    assert "VEC-002" in fail_codes(report)  # index DIMENSION 4 != declared 8
    assert "VEC-010" in fail_codes(report)  # sampled embeddings are 4-dim


async def test_noticias_mini_metric_mismatch(database):
    seed(database, "noticias_mini")
    report = await check(build_noticias(metric="euclidean"), database)
    assert "VEC-003" in fail_codes(report)


async def test_noticias_mini_missing_vector_index(database):
    seed(database, "noticias_mini")
    sql(database, "REMOVE INDEX idx_vec ON TABLE noticia;")
    report = await check(build_noticias(), database)
    assert "VEC-001" in fail_codes(report)


async def test_noticias_mini_wrong_analyzer_declared(database):
    seed(database, "noticias_mini")
    report = await check(build_noticias(analyzer="az_ingles"), database)
    assert "FTS-002" in fail_codes(report)


async def test_noticias_mini_missing_edge_table(database):
    seed(database, "noticias_mini")
    sql(database, "REMOVE TABLE cita;")
    report = await check(build_noticias(), database)
    assert "REL-001" in fail_codes(report)
    finding = next(f for f in report.findings if f.code == "REL-001")
    assert "does not exist" in finding.message  # the canonical message: table declared but absent


async def test_implicit_any_edge_warns(database):
    seed(database, "noticias_mini")
    # replace a typed edge with an implicit RELATE table (bench A4)
    sql(
        database,
        "REMOVE TABLE sobre; RELATE noticia:n1->sobre->tema:t1; RELATE noticia:n2->sobre->tema:t2;",
    )
    report = await check(build_noticias(), database)
    assert "WARN" in statuses(report, "REL-002")
    warn = next(f for f in report.findings if f.code == "REL-002" and f.status == "WARN")
    assert "TYPE ANY" in warn.message


async def test_report_json_serializes(database):
    seed(database, "degrau1")
    report = await check(degrau1_ontology(), database)
    parsed = json.loads(report.model_dump_json())
    assert parsed["namespace"] == NS
    assert parsed["not_verified"]
