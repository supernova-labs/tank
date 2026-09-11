"""Golden ontology — neutral domain (engineering reports)."""

from tank import Attr, Locator, Ontology, StableId, UnitType

ontology = Ontology(
    types=[
        UnitType(
            "laudo",
            table="parecer_tecnico",
            nature="original",
            id=StableId.of("codigo"),
            text="corpo_texto",
            locator=Locator(source="codigo"),
            attrs=[
                Attr("situacao", "string", values=["vigente", "revogado"]),
                Attr("emitido_em", "datetime"),
            ],
        ),
    ],
)
