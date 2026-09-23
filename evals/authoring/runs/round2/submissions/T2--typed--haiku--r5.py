from typing import Annotated

from tank import (
    Key,
    Locate,
    Link,
    Named,
    Text,
    Unit,
    Ontology,
)


class Manual(Unit, table="manual"):
    title: Annotated[str, Key()]
    body: Annotated[str, Text()]


class Chunk(Unit, table="chunk"):
    pos: Annotated[int, Locate(role="order")]
    content: Annotated[str, Text()]
    manual: Annotated[Link[Manual], Named("chunk_of"), Locate(role="source")]


ontology = Ontology.of(Manual, Chunk)
