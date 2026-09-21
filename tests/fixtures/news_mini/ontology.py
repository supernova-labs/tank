"""news_mini ontology — a complete news-graph example.

``build()`` exists so integration tests can produce *ontology-side* mutations
(wrong dim, wrong analyzer, wrong link field) without touching the database seed.
"""

from tank import (
    Attr,
    Freshness,
    FullText,
    Ontology,
    Relation,
    Scope,
    StableId,
    UnitType,
    Vector,
    Weight,
)


def build(
    dim: int = 4,
    metric: str = "cosine",
    analyzer: str = "az_en",
    feed_field: str = "feed",
) -> Ontology:
    return Ontology(
        types=[
            UnitType(
                "news",
                table="news",
                nature="original",
                id=StableId.of("title", "published_at"),
                text="body",
                attrs=[Attr("title", "string"), Attr("published_at", "datetime")],
                vector=Vector("emb", dim, metric),
                fulltext=FullText("body", analyzer=analyzer, language="english"),
            ),
            UnitType(
                "entity",
                table="entity",
                attrs=[
                    Attr("name", "string"),
                    Attr("kind", "string", values=["person", "agency", "organization"]),
                ],
            ),
            UnitType("topic", table="topic", attrs=[Attr("name", "string")]),
            UnitType(
                "document",
                table="document",
                attrs=[
                    Attr("number", "string"),
                    Attr("status", "string", values=["pending", "approved", "rejected"]),
                ],
            ),
            UnitType("feed", table="feed", attrs=[Attr("name", "string")]),
        ],
        relations=[
            Relation("mentions", "news", "entity", weight=Weight("relevance")),
            Relation("about", "news", "topic"),
            Relation("cites", "news", "document"),
            Relation("from_feed", "news", "feed", kind="field_link", field=feed_field),
        ],
        scopes=[Scope("entity", via="mentions")],
        freshness=[Freshness("news", "published_at", "30d")],
    )


ontology = build()
