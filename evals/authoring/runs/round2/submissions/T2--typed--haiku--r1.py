from typing import Annotated

from tank import Unit, Link, Key, Text, Locate, Named, Ontology


class Manual(Unit, table="manual"):
    title: Annotated[str, Key()]
    body: Annotated[str, Text()]


class Chunk(Unit, table="chunk"):
    content: Annotated[str, Text()]
    pos: Annotated[int, Locate(role="order")]
    manual: Annotated[Link[Manual], Named("chunk_of"), Locate(role="source")]


ontology = Ontology.of(Manual, Chunk)
