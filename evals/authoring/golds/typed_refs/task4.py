"""Typed reference translation of task 4 (task 2 + additions) — verification only."""

from typing import Annotated, Literal

from tank import Ontology
from tank.typed import Edge, Key, Link, Locate, Named, Text, Unit


class Manual(Unit, table="manual"):
    title: Annotated[str, Key()]
    body: Annotated[str, Text()]


class Chunk(Unit, table="chunk"):
    content: Annotated[str, Text()]
    pos: Annotated[int, Locate("order")]
    manual: Annotated[Link[Manual], Named("chunk_of"), Locate("source")]


class Faq(Unit, table="faq"):
    question: Annotated[str, Key()]
    answer: Annotated[str, Text()]
    tag: Literal["howto", "billing", "bug"]


class CoversManual(Edge, src=Faq, dst=Manual):
    pass


ontology = Ontology.of(Manual, Chunk, Faq, CoversManual)
