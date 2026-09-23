"""Ontology declaration for the T2 template brief.

Two unit types: `manual` (an original document, identified by its title, no
searchable indexes) and `chunk` (an original fragment of a manual, linked back
to it by a field_link relation with no weight, positioned by `pos`).
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
            nature="original",
            id=StableId.of("title"),
            text="body",
            attrs=[Attr("title", "string")],
        ),
        UnitType(
            "chunk",
            table="chunk",
            nature="original",
            text="content",
            attrs=[Attr("pos", "int")],
            locator=Locator(source="manual", order="pos"),
        ),
    ],
    relations=[
        Relation("chunk_of", "chunk", "manual", kind="field_link", field="manual"),
    ],
)
