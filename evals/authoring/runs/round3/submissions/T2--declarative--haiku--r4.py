from tank import (
    Attr,
    Ontology,
    Relation,
    StableId,
    UnitType,
    Locator,
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
