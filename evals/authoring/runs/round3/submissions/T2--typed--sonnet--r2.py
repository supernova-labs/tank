"""Product documentation ontology: manual / chunk, declared as typed classes."""

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
    pos: Annotated[int, Locate("order")]
    manual: Annotated[Link[Manual], Named("chunk_of"), Locate("source")]


ontology = Ontology.of(
    Manual,
    Chunk,
)
