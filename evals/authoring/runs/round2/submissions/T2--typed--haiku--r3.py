"""Product documentation ontology declared with typed classes."""

from typing import Annotated

from tank import (
    Key,
    Link,
    Locate,
    Named,
    Ontology,
    Searchable,
    Text,
    Unit,
)


class Manual(Unit, table="manual"):
    """A product manual."""

    title: Annotated[str, Key()]
    body: Annotated[str, Text()]


class Chunk(Unit, table="chunk"):
    """A chunk within a manual."""

    content: Annotated[str, Text()]
    pos: Annotated[int, Locate(role="order")]
    manual: Annotated[Link[Manual], Named("chunk_of"), Locate(role="source")]


ontology = Ontology.of(Manual, Chunk)
