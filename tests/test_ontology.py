"""Static ONT-* checks: a broken ontology must fail at construction, with every
violation reported at once. Fixtures use a neutral domain (engineering
assessments), never a real consumer's schema.
"""

import json

import pytest
from pydantic import ValidationError

from tank import (
    Attr,
    Freshness,
    FullText,
    Locator,
    Ontology,
    OntologyError,
    Relation,
    Scope,
    StableId,
    UnitType,
    Vector,
    Weight,
)


def ont(**kwargs) -> Ontology:
    """An ontology with the stamp filled in — for tests that are about something else.

    Tests that are *about* the stamp build ``Ontology`` directly.
    """
    kwargs.setdefault("name", "assessments")
    kwargs.setdefault("version", "0.1.0")
    return Ontology(**kwargs)


def report_type(**overrides) -> UnitType:
    base = {
        "name": "report",
        "table": "technical_assessment",
        "nature": "original",
        "id": StableId.of("code"),
        "text": "body_text",
        "locator": Locator(source="code"),
        "attrs": [
            Attr("status", "string", values=["current", "revoked"]),
            Attr("issued_at", "datetime"),
        ],
    }
    base.update(overrides)
    return UnitType(**base)


def test_valid_minimal_ontology_builds():
    ontology = ont(types=[report_type()])
    assert ontology.type_named("report").table == "technical_assessment"


def test_positional_style_is_supported():
    unit = UnitType("report", table="technical_assessment")
    assert unit.name == "report"
    rel = Relation("issued_by", "report", "engineer")
    assert (rel.from_, rel.to) == ("report", "engineer")


def test_declared_fields_collects_everything():
    unit = report_type(
        vector=Vector("emb", 4, "cosine"),
        fulltext=FullText("body_text"),
    )
    assert unit.declared_fields() == {"code", "body_text", "status", "issued_at", "emb"}


def test_stable_id_distinguishes_identity_from_version_fields():
    sid = StableId.of("source", "chunk_order", version=["text_version", "chunker_version"])
    assert sid.fields == ["source", "chunk_order"]
    assert sid.version_fields == ["text_version", "chunker_version"]
    unit = report_type(id=sid)
    assert {"source", "chunk_order", "text_version", "chunker_version"} <= unit.declared_fields()


def test_duplicate_type_name_is_ont001():
    with pytest.raises(OntologyError) as err:
        ont(types=[report_type(), report_type()])
    assert [v.code for v in err.value.violations] == ["ONT-001"]


def test_relation_to_unknown_type_is_ont002_and_reports_all_violations():
    with pytest.raises(OntologyError) as err:
        ont(
            types=[report_type()],
            relations=[Relation("issued_by", "report", "engineer")],
            scopes=[Scope("site", via="belongs_to")],
        )
    codes = sorted(v.code for v in err.value.violations)
    assert codes == ["ONT-002", "ONT-003"]  # both reported in one raise


def test_scope_without_via_is_fine():
    ont(types=[report_type()], scopes=[Scope("assessment")])


def test_freshness_on_unknown_type_is_ont008():
    with pytest.raises(OntologyError) as err:
        ont(types=[report_type()], freshness=[Freshness("news", "issued_at", "30d")])
    assert err.value.violations[0].code == "ONT-008"


def test_duplicate_attr_is_ont005():
    bad = report_type(attrs=[Attr("status", "string"), Attr("status", "string")])
    with pytest.raises(OntologyError) as err:
        ont(types=[bad])
    assert err.value.violations[0].code == "ONT-005"


def test_vector_requires_positive_dim_and_known_metric():
    with pytest.raises(ValueError):
        Vector("emb", 0)
    with pytest.raises(ValueError):
        Vector("emb", 4, "chebyshev")  # not an HNSW metric


def test_empty_attr_values_rejected():
    with pytest.raises(ValueError):
        Attr("status", "string", values=[])
    with pytest.raises(ValueError):
        Attr("status", "string", values={})


def test_attr_values_as_mapping():
    attr = Attr("status", "string", values={"c_04": "published", "c_11": "killed"})
    assert attr.value_codes() == ["c_04", "c_11"]
    assert Attr("status", "string", values=["current", "revoked"]).value_codes() == [
        "current",
        "revoked",
    ]
    with pytest.raises(ValueError):
        Attr("status", "string", values={"c_04": ""})


def test_edge_relation_defaults_table_to_name():
    rel = Relation("issued_by", "report", "engineer")
    assert rel.kind == "edge" and rel.table == "issued_by"


def test_field_link_requires_field_and_rejects_weight():
    rel = Relation("of_project", "report", "project", kind="field_link", field="project")
    assert rel.field == "project"
    with pytest.raises(ValueError):
        Relation("of_project", "report", "project", kind="field_link")
    with pytest.raises(ValueError):
        Relation(
            "of_project",
            "report",
            "project",
            kind="field_link",
            field="project",
            weight=Weight("relevance"),
        )


def test_field_link_colliding_with_scalar_attr_is_ont009():
    report = report_type(attrs=[Attr("project", "string")])
    project = UnitType("project", table="project")
    with pytest.raises(OntologyError) as err:
        ont(
            types=[report, project],
            relations=[
                Relation("of_project", "report", "project", kind="field_link", field="project")
            ],
        )
    assert err.value.violations[0].code == "ONT-009"


def test_locator_rejects_non_string_fields():
    with pytest.raises(ValueError):
        Locator(source=123)


def test_json_export_round_trips():
    ontology = Ontology(
        name="assessments",
        version="0.1.0",
        types=[report_type(vector=Vector("emb", 4), fulltext=FullText("body_text"))],
        scopes=[Scope("assessment")],
        freshness=[Freshness("report", "issued_at", "30d")],
    )
    data = json.loads(ontology.to_json())
    assert data["types"][0]["table"] == "technical_assessment"
    assert data["types"][0]["vector"]["dim"] == 4
    rebuilt = Ontology(**data)
    assert rebuilt.type_named("report").vector.metric == "cosine"


# ----------------------------------------------------- the stamp, and strictness


def test_ontology_requires_a_name_and_a_version():
    """Both carry no default on purpose.

    A default would give every project that forgot to set them the same
    identity — one wrong answer, handed out repeatedly.
    """
    with pytest.raises(ValidationError):
        Ontology(types=[report_type()])
    with pytest.raises(ValidationError):
        Ontology(name="assessments", types=[report_type()])
    with pytest.raises(ValidationError):
        Ontology(version="0.1.0", types=[report_type()])
    with pytest.raises(ValidationError):
        Ontology(name="", version="0.1.0", types=[report_type()])


def test_the_stamp_is_retained_not_silently_dropped():
    """The regression this exists for: with pydantic's default (`extra="ignore"`)
    the two keywords below were accepted and thrown away, so the obvious attempt
    to version a declaration failed while looking like it had worked."""
    ontology = Ontology(name="assessments", version="0.3.0", types=[report_type()])
    assert (ontology.name, ontology.version) == ("assessments", "0.3.0")
    assert ontology.stamp().startswith("assessments@0.3.0+")


def test_unknown_keyword_is_rejected_rather_than_ignored():
    """`extra="forbid"` across the declaration models. A typo that is silently
    dropped produces a declaration that is missing what its author wrote — and
    nothing anywhere says so."""
    with pytest.raises(ValidationError):
        UnitType("report", table="technical_assessment", natrue="derived")
    with pytest.raises(ValidationError):
        Attr("status", "string", value=["current"])
    with pytest.raises(ValidationError):
        ont(types=[report_type()], scope=[Scope("assessment")])


def test_locator_stays_free_form():
    """`Locator` is the one model whose keywords are the data. It keeps
    `extra="allow"`, and the strictness above must not have reached it."""
    locator = Locator(source="code", order="chunk_order", anything="else")
    assert locator.fields() == {"source": "code", "order": "chunk_order", "anything": "else"}
