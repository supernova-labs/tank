"""Typed ontology declaration for the product documentation system:
manuals and their chunks.
"""

from typing import Annotated

from tank import Key, Link, Locate, Named, Ontology, Text, Unit


class Manual(Unit, table="manual", nature="original"):
    title: Annotated[str, Key()]
    body: Annotated[str, Text()]


class Chunk(Unit, table="chunk", nature="original"):
    content: Annotated[str, Text()]
    pos: Annotated[int, Locate("order")]
    manual: Annotated[Link[Manual], Locate("source"), Named("chunk_of")]


ontology = Ontology.of(Manual, Chunk)
