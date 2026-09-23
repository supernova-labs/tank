"""Existing ontology of the docs project (typed form). Task 4 extends it."""

from typing import Annotated, Literal

from tank import Edge, Key, Link, Locate, Named, Ontology, Searchable, Text, Unit


class Manual(Unit, table="manual"):
    title: Annotated[str, Key()]
    body: Annotated[str, Text()]


class Chunk(Unit, table="chunk"):
    content: Annotated[str, Text()]
    pos: Annotated[int, Locate("order")]
    manual: Annotated[Link[Manual], Named("chunk_of"), Locate("source")]


class Faq(Unit, table="faq"):
    question: Annotated[str, Key()]
    tag: Literal["howto", "billing", "bug"]
    answer: Annotated[str, Text()]


class CoversManual(Edge, src=Faq, dst=Manual):
    pass


ontology = Ontology.of(Manual, Chunk, Faq, CoversManual)
