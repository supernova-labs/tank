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

ontology = Ontology(
    types=[
        UnitType(
            "author",
            table="author",
            nature="original",
            attrs=[Attr("name", "string")],
        ),
        UnitType(
            "kb_article",
            table="kb_article",
            nature="original",
            id=StableId.of("slug"),
            text="body",
            attrs=[
                Attr("slug", "string"),
                Attr("status", "string", values=["draft", "published", "archived"]),
                Attr("updated_at", "datetime"),
            ],
            vector=Vector("emb", 8, "cosine"),
            fulltext=FullText("body", analyzer="az_kb", language="english"),
        ),
        UnitType(
            "summary",
            table="summary",
            nature="derived",
            text="text",
            attrs=[Attr("created_at", "datetime")],
        ),
    ],
    relations=[
        Relation(
            "summarizes",
            "summary",
            "kb_article",
            kind="field_link",
            field="article",
        ),
        Relation(
            "written_by",
            "kb_article",
            "author",
            table="written_by",
            weight=Weight("share", higher_is_better=True),
        ),
    ],
    scopes=[Scope("author", via="written_by")],
    freshness=[Freshness("kb_article", "updated_at", "45d")],
)
