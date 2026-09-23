"""Typed declaration for the T2 brief (manual / chunk / chunk_of)."""

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


class Manual(Unit, table="manual", nature="original"):
    title: Annotated[str, Key()]
    body: Annotated[str, Text()]


class Chunk(Unit, table="chunk", nature="original"):
    content: Annotated[str, Text()]
    pos: Annotated[int, Locate(role="order")]
    manual: Annotated[Link[Manual], Named("chunk_of"), Locate(role="source")]


ontology = Ontology.of(
    Manual,
    Chunk,
)
