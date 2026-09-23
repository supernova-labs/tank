"""Product documentation ontology declared with typed Tank API."""

from typing import Annotated

from tank import Key, Link, Locate, Named, Ontology, Text, Unit


class Manual(Unit, table="manual"):
    """A product manual document."""

    title: Annotated[str, Key()]
    body: Annotated[str, Text()]


class Chunk(Unit, table="chunk"):
    """A chunk of content within a manual."""

    content: Annotated[str, Text()]
    pos: Annotated[int, Locate("order")]
    manual: Annotated[Link[Manual], Named("chunk_of"), Locate("source")]


ontology = Ontology.of(Manual, Chunk)
