"""Gold IR for task 2."""

from tank import Attr, Locator, Ontology, Relation, StableId, UnitType


def build() -> Ontology:
    return Ontology(
        name="gold_task2",
        version="1.0.0",
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
        ],
        relations=[Relation("chunk_of", "chunk", "manual", kind="field_link", field="manual")],
    )
