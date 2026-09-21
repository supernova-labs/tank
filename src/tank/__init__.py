"""Tank — make your content accessible to agents, and prove it is being used well.

v0.1 ships the ontology-as-code contract and the deterministic validator
(`tank check`). See docs/rag-vision.md for the full thesis.
"""

from tank.ontology import (
    Attr,
    Freshness,
    FullText,
    Locator,
    Ontology,
    OntologyError,
    Relation,
    Scope,
    StableId,
    UnitType,
    Vector,
    Violation,
    Weight,
)

__all__ = [
    "Attr",
    "Freshness",
    "FullText",
    "Locator",
    "Ontology",
    "OntologyError",
    "Relation",
    "Scope",
    "StableId",
    "UnitType",
    "Vector",
    "Violation",
    "Weight",
]

__version__ = "0.1.0"
