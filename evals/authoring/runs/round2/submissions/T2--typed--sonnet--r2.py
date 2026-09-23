"""Product documentation ontology: manuals and their chunks."""

from typing import Annotated

from tank import (
    Key,
    Link,
    Locate,
    Named,
    Ontology,
    Text,
    Unit,
)


class Manual(Unit, table="manual"):
    body: Annotated[str, Text()]
    title: Annotated[str, Key()]


class Chunk(Unit, table="chunk"):
    content: Annotated[str, Text()]
    pos: Annotated[int, Locate(role="order")]
    manual: Annotated[Link[Manual], Named("chunk_of"), Locate(role="source")]


ontology = Ontology.of(
    Manual,
    Chunk,
)
