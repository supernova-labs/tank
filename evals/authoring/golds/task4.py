"""Gold IR for task 4 (task 2 + faq + covers_manual)."""

from tank import Attr, Locator, Ontology, Relation, StableId, UnitType


def build() -> Ontology:
    return Ontology(
        types=[
            UnitType(
                "manual",
                table="manual",
                id=StableId.of("title"),
                text="body",
                attrs=[Attr("title", "string")],
            ),
            UnitType(
                "chunk",
                table="chunk",
                text="content",
                attrs=[Attr("pos", "int")],
                locator=Locator(source="manual", order="pos"),
            ),
            UnitType(
                "faq",
                table="faq",
                id=StableId.of("question"),
                text="answer",
                attrs=[
                    Attr("question", "string"),
                    Attr("tag", "string", values=["howto", "billing", "bug"]),
                ],
            ),
        ],
        relations=[
            Relation("chunk_of", "chunk", "manual", kind="field_link", field="manual"),
            Relation("covers_manual", "faq", "manual"),
        ],
    )
