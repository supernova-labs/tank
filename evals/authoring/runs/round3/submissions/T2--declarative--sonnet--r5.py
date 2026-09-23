"""Ontology declaration for the product-documentation project.

Two findable types — ``manual`` and ``chunk`` — connected by the ``chunk_of``
relation (each chunk points at its manual through the record field ``manual``).
"""

from tank import (
    Attr,
    Locator,
    Ontology,
    Relation,
    StableId,
    UnitType,
)

ontology = Ontology(
    types=[
        UnitType(
            "manual",
            table="manual",
            id=StableId.of("title"),
            text="body",
            attrs=[Attr("title", "string")],
        ),
        UnitType(
            "chunk",
            table="chunk",
            text="content",
            attrs=[Attr("pos", "int")],
            locator=Locator(source="manual", order="pos"),
        ),
    ],
    relations=[
        Relation("chunk_of", "chunk", "manual", kind="field_link", field="manual"),
    ],
)
