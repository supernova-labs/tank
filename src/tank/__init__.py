"""Tank — make your content accessible to agents, and prove it is being used well.

v0.1 ships the ontology-as-code contract and the deterministic validator
(`tank check`). See docs/rag-vision.md for the full thesis.

The declarative form exported here is the public way to declare an ontology.
A typed form, where plain pydantic classes carry the declaration, lives in
``tank.typed`` and is imported explicitly:

    from tank.typed import Unit, Edge, Key, Text

It is deliberately not re-exported from this namespace. Its markers carry
generic names (``Text``, ``Key``, ``Link``, ``Version``, ``Embedding``) that
collide with half the ecosystem at the top level, and a name in ``__all__``
is a promise: removing one later is a breaking change, while adding one never
is. The two forms produce the same declaration, and ``tests/test_typed.py``
holds them to that.
"""

from tank.ontology import (
    Attr,
    Freshness,
    FullText,
    Locator,
    Ontology,
    OntologyError,
    Relation,
    Rendered,
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
    "Rendered",
    "Scope",
    "StableId",
    "UnitType",
    "Vector",
    "Violation",
    "Weight",
]

__version__ = "0.1.0"
