from typing import Annotated

from tank import Key, Link, Locate, Named, Ontology, Text, Unit


class Manual(Unit, table="manual"):
    title: Annotated[str, Key()]
    body: Annotated[str, Text()]


class Chunk(Unit, table="chunk"):
    manual: Annotated[Link[Manual], Named("chunk_of"), Locate(role="source")]
    pos: Annotated[int, Locate(role="order")]
    content: Annotated[str, Text()]


ontology = Ontology.of(Manual, Chunk)
