"""Product documentation ontology: manually and chunks."""

from typing import Annotated

from tank import (
    Key,
    Locate,
    Link,
    Named,
    Ontology,
    Text,
    Unit,
)


class Manual(Unit, table="manual"):
    title: Annotated[str, Key()]
    body: Annotated[str, Text()]


class Chunk(Unit, table="chunk"):
    content: Annotated[str, Text()]
    pos: Annotated[int, Locate(role="order")]
    manual: Annotated[Link[Manual], Named("chunk_of"), Locate(role="source")]


ontology = Ontology.of(
    Manual,
    Chunk,
)
