"""Declaration for T1--template--w2: ticket unit type."""

from tank import (
    Attr,
    Ontology,
    StableId,
    UnitType,
)

ontology = Ontology(
    types=[
        UnitType(
            "ticket",
            table="ticket",
            nature="original",
            id=StableId.of("subject", "opened_at"),
            text="body",
            attrs=[
                Attr("subject", "string"),
                Attr("priority", "string", values=["p1", "p2", "p3"]),
                Attr("opened_at", "datetime"),
            ],
        ),
    ],
)
