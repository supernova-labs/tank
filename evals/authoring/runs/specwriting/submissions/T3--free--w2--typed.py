"""Knowledge base ontology: articles, their authors, and machine-written
summaries of articles."""

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


class Author(Unit, table="author", nature="original"):
    name: str


class KbArticle(Unit, table="kb_article", nature="original"):
    slug: Annotated[str, Key()]
    body: Annotated[str, Text(), Searchable(analyzer="az_kb", language="english")]
    status: Literal["draft", "published", "archived"]
    updated_at: Annotated[datetime, Ages("45d")]
    emb: Embedding[8] | None = None  # metric defaults to cosine


class Summary(Unit, table="summary", nature="derived"):
    text: Annotated[str, Text()]
    created_at: datetime
    article: Annotated[Link[KbArticle], Named("summarizes")]


class WrittenBy(Edge, src=KbArticle, dst=Author, table="written_by"):
    share: Annotated[float, Weighted(higher_is_better=True)]


ontology = Ontology.of(
    Author,
    KbArticle,
    Summary,
    WrittenBy,
    scopes=[Scope("author", via="written_by")],
)
