"""Gold IR for task 1 (declarative form is the reference representation)."""

from tank import Attr, Ontology, StableId, UnitType


def build() -> Ontology:
    return Ontology(
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
            )
        ]
    )
