"""Static ONT-* checks: a broken ontology must fail at construction, with every
violation reported at once. Fixtures use a neutral domain (engineering reports),
never a real consumer's schema.
"""

import json

import pytest

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


def laudo_type(**overrides) -> UnitType:
    base = {
        "name": "laudo",
        "table": "parecer_tecnico",
        "nature": "original",
        "id": StableId.of("codigo"),
        "text": "corpo_texto",
        "locator": Locator(source="codigo"),
        "attrs": [
            Attr("situacao", "string", values=["vigente", "revogado"]),
            Attr("emitido_em", "datetime"),
        ],
    }
    base.update(overrides)
    return UnitType(**base)


def test_valid_degrau1_ontology_builds():
    ont = Ontology(types=[laudo_type()])
    assert ont.type_named("laudo").table == "parecer_tecnico"


def test_positional_style_matches_vision_doc():
    unit = UnitType("laudo", table="parecer_tecnico")
    assert unit.name == "laudo"
    rel = Relation("emitido_por", "laudo", "responsavel")
    assert (rel.from_, rel.to) == ("laudo", "responsavel")


def test_declared_fields_collects_everything():
    unit = laudo_type(
        vector=Vector("emb", 4, "cosine"),
        fulltext=FullText("corpo_texto"),
    )
    assert unit.declared_fields() == {"codigo", "corpo_texto", "situacao", "emitido_em", "emb"}


def test_duplicate_type_name_is_ont001():
    with pytest.raises(OntologyError) as err:
        Ontology(types=[laudo_type(), laudo_type()])
    assert [v.code for v in err.value.violations] == ["ONT-001"]


def test_relation_to_unknown_type_is_ont002_and_reports_all_violations():
    with pytest.raises(OntologyError) as err:
        Ontology(
            types=[laudo_type()],
            relations=[Relation("emitido_por", "laudo", "responsavel")],
            scopes=[Scope("obra", via="pertence_a")],
        )
    codes = sorted(v.code for v in err.value.violations)
    assert codes == ["ONT-002", "ONT-003"]  # both reported in one raise


def test_scope_without_via_is_fine():
    Ontology(types=[laudo_type()], scopes=[Scope("parecer")])


def test_freshness_on_unknown_type_is_ont008():
    with pytest.raises(OntologyError) as err:
        Ontology(types=[laudo_type()], freshness=[Freshness("noticia", "emitido_em", "30d")])
    assert err.value.violations[0].code == "ONT-008"


def test_duplicate_attr_is_ont005():
    bad = laudo_type(attrs=[Attr("situacao", "string"), Attr("situacao", "string")])
    with pytest.raises(OntologyError) as err:
        Ontology(types=[bad])
    assert err.value.violations[0].code == "ONT-005"


def test_vector_requires_positive_dim_and_known_metric():
    with pytest.raises(ValueError):
        Vector("emb", 0)
    with pytest.raises(ValueError):
        Vector("emb", 4, "chebyshev")  # not an HNSW metric (bancada A2/V1-V7)


def test_empty_attr_values_rejected():
    with pytest.raises(ValueError):
        Attr("situacao", "string", values=[])


def test_edge_relation_defaults_table_to_name():
    rel = Relation("emitido_por", "laudo", "responsavel")
    assert rel.kind == "edge" and rel.table == "emitido_por"


def test_field_link_requires_field_and_rejects_weight():
    rel = Relation("do_projeto", "laudo", "projeto", kind="field_link", field="projeto")
    assert rel.field == "projeto"
    with pytest.raises(ValueError):
        Relation("do_projeto", "laudo", "projeto", kind="field_link")
    with pytest.raises(ValueError):
        Relation(
            "do_projeto",
            "laudo",
            "projeto",
            kind="field_link",
            field="projeto",
            weight=Weight("peso"),
        )


def test_field_link_colliding_with_scalar_attr_is_ont009():
    laudo = laudo_type(attrs=[Attr("projeto", "string")])
    projeto = UnitType("projeto", table="projeto")
    with pytest.raises(OntologyError) as err:
        Ontology(
            types=[laudo, projeto],
            relations=[
                Relation("do_projeto", "laudo", "projeto", kind="field_link", field="projeto")
            ],
        )
    assert err.value.violations[0].code == "ONT-009"


def test_locator_rejects_non_string_fields():
    with pytest.raises(ValueError):
        Locator(source=123)


def test_json_export_round_trips():
    ont = Ontology(
        types=[laudo_type(vector=Vector("emb", 4), fulltext=FullText("corpo_texto"))],
        scopes=[Scope("parecer")],
        freshness=[Freshness("laudo", "emitido_em", "30d")],
    )
    data = json.loads(ont.to_json())
    assert data["types"][0]["table"] == "parecer_tecnico"
    assert data["types"][0]["vector"]["dim"] == 4
    rebuilt = Ontology(**data)
    assert rebuilt.type_named("laudo").vector.metric == "cosine"
