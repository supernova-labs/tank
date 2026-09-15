"""Minimal golden ontology — neutral domain (engineering assessments)."""

from tank import Attr, Locator, Ontology, StableId, UnitType

ontology = Ontology(
    types=[
        UnitType(
            "report",
            table="technical_assessment",
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
