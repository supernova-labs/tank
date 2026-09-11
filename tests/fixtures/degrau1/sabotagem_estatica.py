"""Sabotage: internally broken ontology — must explode on import (ONT-*), no DB needed."""

from tank import Ontology, Relation, Scope, UnitType

ontology = Ontology(
    types=[UnitType("laudo", table="parecer_tecnico")],
    relations=[Relation("emitido_por", "laudo", "responsavel")],  # ONT-002: unknown type
    scopes=[Scope("obra", via="pertence_a")],  # ONT-003: unknown relation
)
