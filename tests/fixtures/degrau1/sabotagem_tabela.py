"""Sabotage: the ontology points at a table that does not exist."""

from tank import Attr, Locator, Ontology, StableId, UnitType

ontology = Ontology(
    types=[
        UnitType(
            "laudo",
            table="parecer_tecnico_v2",  # <- does not exist in the database
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
