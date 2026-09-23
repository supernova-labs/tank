"""Typed ontology declaration for T3--template--w1."""

from datetime import datetime
from typing import Annotated, Literal

from tank import (
    Ages,
    Edge,
    Embed,
    Embedding,
    Key,
    Link,
    Named,
    Ontology,
    Scope,
    Searchable,
    Text,
    Unit,
    Weighted,
)


class Author(Unit, table="author"):
    name: str


class KbArticle(Unit, table="kb_article", nature="original"):
    slug: Annotated[str, Key()]
    status: Literal["draft", "published", "archived"]
    updated_at: Annotated[datetime, Ages("45d")]
    body: Annotated[str, Text(), Searchable(analyzer="az_kb", language="english")]
    emb: Annotated[Embedding[8], Embed(metric="cosine")] | None = None


class Summary(Unit, table="summary", nature="derived"):
    created_at: datetime
    text: Annotated[str, Text()]
    article: Annotated[Link[KbArticle], Named("summarizes")]


class WrittenBy(Edge, src=KbArticle, dst=Author, name="written_by"):
    share: Annotated[float, Weighted(higher_is_better=True)]


ontology = Ontology.of(
    Author,
    KbArticle,
    Summary,
    WrittenBy,
    scopes=[Scope("author", via="written_by")],
)
