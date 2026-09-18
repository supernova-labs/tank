"""Tank — make your content accessible to agents, and prove it is being used well.

v0.1 ships the ontology-as-code contract — declared as typed classes
(``Unit``/``Edge``, see ``tank.typed``) — and the deterministic validator
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
    Rendered,
    Scope,
    StableId,
    UnitType,
    Vector,
    Violation,
    Weight,
)
from tank.typed import (
    Ages,
    DeclarationError,
    Edge,
    Embed,
    Embedding,
    Hidden,
    Key,
    Link,
    Locate,
    Named,
    Searchable,
    Text,
    Unit,
    Version,
    Weighted,
    rendered_text,
)

__all__ = [
    "Ages",
    "Attr",
    "DeclarationError",
    "Edge",
    "Embed",
    "Embedding",
    "Freshness",
    "FullText",
    "Hidden",
    "Key",
    "Link",
    "Locate",
    "Locator",
    "Named",
    "Ontology",
    "OntologyError",
    "Relation",
    "Rendered",
    "Scope",
    "Searchable",
    "StableId",
    "Text",
    "Unit",
    "UnitType",
    "Vector",
    "Version",
    "Violation",
    "Weight",
    "Weighted",
    "rendered_text",
]

__version__ = "0.1.0"
