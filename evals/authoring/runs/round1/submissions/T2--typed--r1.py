"""Product documentation ontology: manual and chunk, typed declaration."""

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
    title: Annotated[str, Key()]
    body: Annotated[str, Text()]


class Chunk(Unit, table="chunk"):
    content: Annotated[str, Text()]
    pos: Annotated[int, Locate("order")]
    manual: Annotated[Link[Manual], Named("chunk_of"), Locate("source")]


ontology = Ontology.of(Manual, Chunk)
