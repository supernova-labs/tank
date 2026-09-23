"""Existing ontology of the docs project (typed form). Task 4 extends it."""

from typing import Annotated, Literal

from tank import Edge, Key, Link, Locate, Named, Ontology, Text, Unit


class Manual(Unit, table="manual"):
    title: Annotated[str, Key()]
    body: Annotated[str, Text()]


class Chunk(Unit, table="chunk"):
    content: Annotated[str, Text()]
    pos: Annotated[int, Locate("order")]
    manual: Annotated[Link[Manual], Named("chunk_of"), Locate("source")]


class FAQ(Unit, table="faq", name="faq"):
    question: Annotated[str, Key()]
    answer: Annotated[str, Text()]
    tag: Literal["howto", "billing", "bug"]


class CoversManual(Edge, src=FAQ, dst=Manual, table="covers_manual"):
    pass


ontology = Ontology.of(Manual, Chunk, FAQ, CoversManual)
