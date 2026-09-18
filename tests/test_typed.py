"""The typed declaration must derive exactly the ontology the declarative
form expresses. Plus: malformed typed declarations, the constructs only the
typed form has (rendered text, multi-target links), and that the derived
ontology drives ``tank check`` unchanged.
"""

import os
import sys
import urllib.error
import urllib.request
import uuid
from datetime import datetime
from pathlib import Path
from typing import Annotated, Literal

import pytest

sys.path.insert(0, str(Path(__file__).parent / "fixtures" / "news_mini"))
import ontology as declarative
import ontology_typed as typed

from tank import (
    Ages,
    DeclarationError,
    Edge,
    Embed,
    Embedding,
    Hidden,
    Key,
    Link,
    Locate,
    Named,
    Ontology,
    OntologyError,
    Rendered,
    Scope,
    Searchable,
    Text,
    Unit,
    Version,
    Weighted,
    rendered_text,
)


def canonical(ontology: Ontology) -> dict:
    """Relations/freshness order is a declaration artifact, not a semantic one."""
    data = ontology.model_dump()
    data["relations"] = sorted(data["relations"], key=lambda r: r["name"])
    data["freshness"] = sorted(data["freshness"], key=lambda f: (f["unit_type"], f["field"]))
    data["types"] = sorted(data["types"], key=lambda t: t["name"])
    return data


# ------------------------------------------------------------- equivalence


def test_typed_news_mini_equals_declarative_news_mini():
    assert canonical(typed.ontology) == canonical(declarative.ontology)


def test_typed_build_matches_declarative_build_for_every_sabotage():
    for kwargs in (
        {},
        {"dim": 8},
        {"metric": "euclidean"},
        {"analyzer": "az_pt"},
        {"feed_field": "feed_ref"},
    ):
        assert canonical(typed.build(**kwargs)) == canonical(declarative.build(**kwargs)), kwargs


def test_json_round_trip_is_the_same_contract_surface():
    assert canonical(Ontology.model_validate_json(typed.ontology.to_json())) == canonical(
        declarative.ontology
    )


# ---------------------------------------------------------------- mapping


def test_field_mapping_rules():
    class Item(Unit, table="item", nature="derived", description="an item"):
        code: Annotated[str, Key()]
        rev: Annotated[int, Version()]
        body: Annotated[str, Text(), Searchable(analyzer="az")]
        title: Annotated[str, Text()]
        status: Literal["a", "b"]
        flag: bool
        when: Annotated[datetime, Ages("7d"), Locate("order")]
        source: Annotated[str, Locate("source")]
        score: float | None = None
        tags: list[str] | None = None
        meta: dict | None = None
        internal: Annotated[str, Hidden()] = ""
        id: str | None = None
        emb: Annotated[Embedding[3], Embed(metric="euclidean", model="m")] | None = None

    unit = Item.unit_type()
    assert unit.name == "item" and unit.table == "item" and unit.nature == "derived"
    assert unit.description == "an item"
    assert unit.id.fields == ["code"] and unit.id.version_fields == ["rev"]
    assert unit.text == ["body", "title"]
    assert unit.fulltext.field == "body" and unit.fulltext.analyzer == "az"
    assert unit.locator.fields() == {"order": "when", "source": "source"}
    assert unit.vector.field == "emb" and unit.vector.dim == 3
    assert unit.vector.metric == "euclidean" and unit.vector.model == "m"
    by_name = {a.name: a for a in unit.attrs}
    assert set(by_name) == {
        "code",
        "rev",
        "status",
        "flag",
        "when",
        "source",
        "score",
        "tags",
        "meta",
    }
    assert by_name["status"].values == ["a", "b"]
    assert by_name["flag"].type == "bool"
    assert by_name["when"].type == "datetime"
    assert by_name["score"].type == "float"
    assert by_name["tags"].type == "array"
    assert by_name["meta"].type == "object"
    assert Item.__tank_freshness__ == [("when", Ages("7d"))]


def test_embedding_defaults_to_cosine_without_embed_marker():
    class V(Unit, table="v"):
        emb: Embedding[8]

    assert V.unit_type().vector.metric == "cosine" and V.unit_type().vector.model is None


def test_class_name_becomes_snake_case_unit_name_unless_overridden():
    class ProductArea(Unit, table="product_area"):
        name: str

    class Other(Unit, table="x", name="custom"):
        name: str

    assert ProductArea.unit_type().name == "product_area"
    assert Other.unit_type().name == "custom"


def test_edge_defaults_and_weight():
    class Src(Unit, table="src"):
        name: str

    class Dst(Unit, table="dst"):
        name: str

    class LinksTo(Edge, src=Src, dst=Dst):
        w: Annotated[float, Weighted(higher_is_better=False, range=(0, 1))]
        note: str = ""  # not part of the ontology, still usable as data

    ontology = Ontology.of(Src, Dst, LinksTo)
    rel = ontology.relations[0]
    assert (rel.name, rel.table, rel.from_, rel.to) == ("links_to", "links_to", "src", "dst")
    assert rel.weight.field == "w" and rel.weight.higher_is_better is False


def test_link_name_defaults_to_field_name_and_named_overrides_it():
    class Parent(Unit, table="parent"):
        name: str

    class Child(Unit, table="child"):
        parent: Link[Parent]
        other: Annotated[Link[Parent], Named("also_parent")]

    names = {(r.name, r.from_, r.to, r.field) for r in Ontology.of(Child, Parent).relations}
    assert names == {
        ("parent", "child", "parent", "parent"),
        ("also_parent", "child", "parent", "other"),
    }


def test_forward_reference_to_a_class_declared_later_in_the_module():
    class Child(Unit, table="child"):
        parent: Link["Parent"]

    class Parent(Unit, table="parent"):
        name: str

    rel = Ontology.of(Child, Parent).relations[0]
    assert (rel.from_, rel.to, rel.field) == ("child", "parent", "parent")


def json_targets(ontology: Ontology, relation: str) -> list[str]:
    data = Ontology.model_validate_json(ontology.to_json())
    return next(r for r in data.relations if r.name == relation).targets()


def test_multi_target_link_and_edge():
    class Source(Unit, table="source"):
        title: str

    class Note(Unit, table="note"):
        title: str
        about: Link[Source, "Note"]  # a note is about a source OR another note (self-ref by name)

    class Mentions(Edge, src=Note, dst=Source | Note):
        pass

    ontology = Ontology.of(Source, Note, Mentions)
    by_name = {r.name: r for r in ontology.relations}
    assert by_name["about"].to == ["source", "note"]
    assert by_name["about"].targets() == ["source", "note"]
    assert by_name["mentions"].to == ["source", "note"]
    assert json_targets(ontology, "about") == ["source", "note"]


def test_rendered_text_becomes_a_computed_declaration():
    class Entity(Unit, table="entity"):
        name: str
        kind: str

        @rendered_text
        def card(self) -> str:
            return f"{self.name} ({self.kind})"

    unit = Entity.unit_type()
    assert unit.text == Rendered(method="card")
    assert unit.declared_fields() == {"name", "kind"}  # nothing structural to verify
    assert Entity(name="ACME", kind="organization").card() == "ACME (organization)"
    assert '"method": "card"' in Ontology.of(Entity).to_json()


def test_typed_classes_are_usable_as_data_models():
    row = {"title": "t", "body": "b", "published_at": "2026-09-01T10:00:00Z", "feed": "feed:f1"}
    news = typed.News(**row)
    assert news.title == "t" and news.feed == "feed:f1" and news.emb is None


# ----------------------------------------------------------------- errors


def test_unit_requires_table():
    with pytest.raises(DeclarationError, match="table"):

        class NoTable(Unit):
            name: str


def test_unknown_class_kwarg_is_rejected():
    with pytest.raises(DeclarationError, match="unknown class arguments"):

        class Bad(Unit, table="bad", tabel="typo"):
            name: str


def test_two_searchable_fields_are_rejected():
    with pytest.raises(DeclarationError, match="only one Searchable"):

        class Bad(Unit, table="bad"):
            a: Annotated[str, Searchable()]
            b: Annotated[str, Searchable()]


def test_markers_in_the_wrong_place_are_rejected():
    with pytest.raises(DeclarationError, match="Embed\\(\\) only applies"):

        class BadEmbed(Unit, table="bad"):
            v: Annotated[list[float], Embed()]

    with pytest.raises(DeclarationError, match="Named\\(\\) only applies"):

        class BadNamed(Unit, table="bad"):
            v: Annotated[str, Named("x")]

    with pytest.raises(DeclarationError, match="Weighted\\(\\) only applies"):

        class BadWeight(Unit, table="bad"):
            v: Annotated[float, Weighted()]


def test_rendered_text_and_text_fields_are_exclusive():
    with pytest.raises(DeclarationError, match="not both"):

        class Bad(Unit, table="bad"):
            body: Annotated[str, Text()]

            @rendered_text
            def card(self) -> str:
                return self.body


def test_embedding_takes_only_the_dimension():
    with pytest.raises(DeclarationError, match="dimension only"):
        Embedding[4, "cosine"]


def test_unmappable_annotation_is_rejected_unless_hidden():
    class Weird:
        pass

    with pytest.raises(DeclarationError, match="cannot map annotation"):

        class Bad(Unit, table="bad", arbitrary_types_allowed=True):
            w: Weird

    class Ok(Unit, table="ok", arbitrary_types_allowed=True):
        w: Annotated[Weird, Hidden()]

    assert Ok.unit_type().attrs == []


def test_link_to_undeclared_class_fails_at_build():
    class Orphan(Unit, table="orphan"):
        name: str

    class Ref(Unit, table="ref"):
        o: Link[Orphan]

    with pytest.raises(DeclarationError, match="not among the declared"):
        Ontology.of(Ref)  # Orphan not passed

    class Ref2(Unit, table="ref2"):
        o: Link["Ghost"]  # noqa: F821 - deliberately undefined

    with pytest.raises(DeclarationError, match="Ghost"):
        Ontology.of(Ref2)


def test_static_ont_checks_still_apply_to_the_derived_ontology():
    class A(Unit, table="a"):
        name: str

    with pytest.raises(OntologyError) as err:
        Ontology.of(A, scopes=[Scope("s", via="nope")])
    assert [v.code for v in err.value.violations] == ["ONT-003"]


# ------------------------------------------------------------ integration

URL = os.environ.get("TANK_TEST_URL", "http://127.0.0.1:8019")


def _server_up() -> bool:
    try:
        urllib.request.urlopen(f"{URL}/version", timeout=2)
        return True
    except (urllib.error.URLError, OSError):
        return False


needs_server = pytest.mark.skipif(not _server_up(), reason="SurrealDB test server not reachable")


@pytest.fixture
def live_db():
    from test_check_integration import sql

    name = f"t_{uuid.uuid4().hex[:12]}"
    sql(name, "DEFINE PARAM $bootstrap VALUE 1;", allow_errors=True)
    sql(name, "DEFINE PARAM $bootstrap2 VALUE 1;")
    yield name
    sql(name, f"REMOVE DATABASE IF EXISTS `{name}`;", allow_errors=True)


@needs_server
async def test_check_reads_the_typed_ontology_exactly_like_the_declarative_one(live_db):
    from test_check_integration import check, seed

    seed(live_db, "news_mini")
    report_typed = await check(typed.ontology, live_db)
    report_decl = await check(declarative.ontology, live_db)

    def strip(report):
        return sorted((f.code, f.status, f.subject, f.message) for f in report.findings)

    assert strip(report_typed) == strip(report_decl)
    assert report_typed.count("FAIL") == 0
    # sabotage from the typed side: wrong dimension in the class
    report_bad = await check(typed.build(dim=8), live_db)
    assert {f.code for f in report_bad.findings if f.status == "FAIL"} >= {"VEC-002", "VEC-010"}


@needs_server
async def test_multi_target_relations_are_checked_against_the_database(live_db):
    from test_check_integration import check, sql

    class Source(Unit, table="source"):
        title: str

    class Note(Unit, table="note"):
        title: str
        about: Link[Source, "Note"]

    class Mentions(Edge, src=Note, dst=Source | Note):
        pass

    sql(
        live_db,
        """
        DEFINE TABLE source SCHEMAFULL; DEFINE FIELD title ON source TYPE string;
        DEFINE TABLE note SCHEMAFULL;   DEFINE FIELD title ON note TYPE string;
        DEFINE FIELD about ON note TYPE option<record<source | note>>;
        DEFINE TABLE mentions TYPE RELATION IN note OUT source | note SCHEMAFULL;
        CREATE source:s1 SET title='s';
        CREATE note:n1 SET title='n1', about=source:s1;
        CREATE note:n2 SET title='n2', about=note:n1;
        RELATE note:n1->mentions->source:s1; RELATE note:n2->mentions->note:n1;
        """,
    )
    report = await check(Ontology.of(Source, Note, Mentions), live_db)
    by_code = {(f.code, f.subject): f.status for f in report.findings}
    assert by_code[("REL-003", "relation:about")] == "PASS"
    assert by_code[("REL-002", "relation:mentions")] == "PASS"
    assert report.count("FAIL") == 0

    # sabotage: the link column only admits sources, the ontology says source | note
    sql(live_db, "DEFINE FIELD OVERWRITE about ON note TYPE option<record<source>>;")
    report = await check(Ontology.of(Source, Note, Mentions), live_db)
    assert {(f.code, f.status) for f in report.findings if f.subject == "relation:about"} == {
        ("REL-003", "FAIL")
    }
