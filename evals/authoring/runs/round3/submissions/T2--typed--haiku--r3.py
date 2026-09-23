"""Product documentation ontology."""

from typing import Annotated

from tank import (
    Key,
    Link,
    Locate,
    Named,
    Text,
    Unit,
    Ontology,
)


class Manual(Unit, table="manual"):
    title: Annotated[str, Key()]
    body: Annotated[str, Text()]


class Chunk(Unit, table="chunk"):
    content: Annotated[str, Text()]
    pos: Annotated[int, Locate(role="order")]
    manual: Annotated[Link[Manual], Locate(role="source"), Named("chunk_of")]


ontology = Ontology.of(
    Manual,
    Chunk,
)
