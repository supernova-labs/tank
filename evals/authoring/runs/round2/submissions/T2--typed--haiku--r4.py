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
    manual: Annotated[Link[Manual], Named("chunk_of"), Locate(role="source")]
    content: Annotated[str, Text()]
    pos: Annotated[int, Locate(role="order")]


ontology = Ontology.of(Manual, Chunk)
