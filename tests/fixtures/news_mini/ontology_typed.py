"""news_mini declared as typed classes — derives the SAME ontology as
``ontology.py`` (the declarative form, kept as the internal representation).
``build()`` mirrors the parameters of the declarative ``build()`` so the
integration sabotages can be replayed against the typed form.
"""

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


def build(
    dim: int = 4,
    metric: str = "cosine",
    analyzer: str = "az_en",
    feed_field: str = "feed",
) -> Ontology:
    # Classes are built inside the function only so the fixture can be
    # parameterized like the declarative one; a real project declares them at
    # module level (see the bottom of this file).

    class Feed(Unit, table="feed"):
        name: str

    if feed_field == "feed":

        class News(Unit, table="news", nature="original"):
            title: Annotated[str, Key()]
            body: Annotated[str, Text(), Searchable(analyzer=analyzer, language="english")]
            published_at: Annotated[datetime, Key(), Ages("30d")]
            emb: Annotated[Embedding[dim], Embed(metric=metric)] | None = None  # type: ignore[valid-type]
            feed: Annotated[Link[Feed], Named("from_feed")]

    else:

        class News(Unit, table="news", nature="original"):
            title: Annotated[str, Key()]
            body: Annotated[str, Text(), Searchable(analyzer=analyzer, language="english")]
            published_at: Annotated[datetime, Key(), Ages("30d")]
            emb: Annotated[Embedding[dim], Embed(metric=metric)] | None = None  # type: ignore[valid-type]
            feed_ref: Annotated[Link[Feed], Named("from_feed")]

    class Entity(Unit, table="entity"):
        name: str
        kind: Literal["person", "agency", "organization"]

    class Topic(Unit, table="topic"):
        name: str

    class Document(Unit, table="document"):
        number: str
        status: Literal["pending", "approved", "rejected"]

    class Mentions(Edge, src=News, dst=Entity):
        relevance: Annotated[float, Weighted()]

    class About(Edge, src=News, dst=Topic):
        pass

    class Cites(Edge, src=News, dst=Document):
        pass

    return Ontology.of(
        News,
        Entity,
        Topic,
        Document,
        Feed,
        Mentions,
        About,
        Cites,
        scopes=[Scope("entity", via="mentions")],
    )


# --- what a real project writes (module level, no parameterization) -----------


class Feed(Unit, table="feed"):
    name: str


class News(Unit, table="news", nature="original"):
    title: Annotated[str, Key()]
    body: Annotated[str, Text(), Searchable(analyzer="az_en", language="english")]
    published_at: Annotated[datetime, Key(), Ages("30d")]
    emb: Embedding[4] | None = None  # metric defaults to cosine
    feed: Annotated[Link[Feed], Named("from_feed")]


class Entity(Unit, table="entity"):
    name: str
    kind: Literal["person", "agency", "organization"]


class Topic(Unit, table="topic"):
    name: str


class Document(Unit, table="document"):
    number: str
    status: Literal["pending", "approved", "rejected"]


class Mentions(Edge, src=News, dst=Entity):
    relevance: Annotated[float, Weighted()]


class About(Edge, src=News, dst=Topic):
    pass


class Cites(Edge, src=News, dst=Document):
    pass


ontology = Ontology.of(
    News,
    Entity,
    Topic,
    Document,
    Feed,
    Mentions,
    About,
    Cites,
    scopes=[Scope("entity", via="mentions")],
)
