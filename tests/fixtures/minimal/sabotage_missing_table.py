"""Sabotage: the ontology points at a table that does not exist."""

from tank import Attr, Locator, Ontology, StableId, UnitType

ontology = Ontology(
    types=[
        UnitType(
            "report",
            table="technical_assessment_v2",  # <- does not exist in the database
            nature="original",
            id=StableId.of("code"),
            text="body_text",
            locator=Locator(source="code"),
            attrs=[
                Attr("status", "string", values=["current", "revoked"]),
                Attr("issued_at", "datetime"),
            ],
        ),
    ],
)
