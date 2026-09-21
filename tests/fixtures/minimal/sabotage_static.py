"""Sabotage: internally broken ontology — must explode on import (ONT-*), no DB needed."""

from tank import Ontology, Relation, Scope, UnitType

ontology = Ontology(
    types=[UnitType("report", table="technical_assessment")],
    relations=[Relation("issued_by", "report", "engineer")],  # ONT-002: unknown type
    scopes=[Scope("site", via="belongs_to")],  # ONT-003: unknown relation
)
