"""Typed declaration for the T2 / w3 brief: manual + chunk with a chunk_of link."""

from typing import Annotated

from tank import (
    Link,
    Locate,
    Key,
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
    manual: Annotated[Link[Manual], Locate(role="source"), Named("chunk_of")]


ontology = Ontology.of(
    Manual,
    Chunk,
)
