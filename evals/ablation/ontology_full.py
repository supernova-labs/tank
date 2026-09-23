"""Full (control) ontology for the newsroom ablation fixture.

Descriptions are deliberately *neutral*: they must not duplicate the information
carried by the component under ablation (`values`, `locator`, `nature`), or
removing that component would not remove the information.
"""

from tank import (
    Attr,
    Freshness,
    Locator,
    Ontology,
    Relation,
    Scope,
    StableId,
    UnitType,
)


def build() -> Ontology:
    return Ontology(
        types=[
            UnitType(
                "article",
                table="article",
                nature="original",
                id=StableId.of("title", "published_at"),
                text="body",
                attrs=[
                    Attr("title", "string"),
                    Attr("desk", "string", description="newsroom desk that produced the piece"),
                    Attr(
                        "status",
                        "string",
                        values=["filed", "spiked", "held"],
                        description="editorial status",
                    ),
                    Attr("published_at", "datetime"),
                ],
                description="a news article",
            ),
            UnitType(
                "passage",
                table="passage",
                nature="original",
                text="content",
                locator=Locator(source="parent", order="take"),
                description="a span of an article's body",
            ),
            UnitType(
                "brief",
                table="brief",
                nature="derived",
                text="text",
                attrs=[
                    Attr("kind", "string", values=["sum", "ang", "chk"]),
                    Attr("created_at", "datetime"),
                ],
                description="short note attached to an article",
            ),
            UnitType("topic", table="topic", attrs=[Attr("name", "string")]),
        ],
        relations=[
            Relation("covers", "article", "topic"),
            Relation("part_of", "passage", "article", kind="field_link", field="parent"),
            Relation("notes_on", "brief", "article", kind="field_link", field="article"),
        ],
        scopes=[Scope("topic", via="covers")],
        freshness=[Freshness("article", "published_at", "30d")],
    )
