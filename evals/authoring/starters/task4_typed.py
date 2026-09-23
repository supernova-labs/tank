"""Existing ontology of the docs project (typed form). Task 4 extends it."""

from typing import Annotated

from tank import Ontology
from tank.typed import Key, Link, Locate, Named, Text, Unit


class Manual(Unit, table="manual"):
    title: Annotated[str, Key()]
    body: Annotated[str, Text()]


class Chunk(Unit, table="chunk"):
    content: Annotated[str, Text()]
    pos: Annotated[int, Locate("order")]
    manual: Annotated[Link[Manual], Named("chunk_of"), Locate("source")]


ontology = Ontology.of(Manual, Chunk)
