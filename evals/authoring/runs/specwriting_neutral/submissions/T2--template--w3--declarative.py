"""T2--template--w3 ontology declaration.

Declared from the brief at
`/Users/gyprado/dev/tank/evals/authoring/runs/specwriting/briefs/T2--template--w3.md`.
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
