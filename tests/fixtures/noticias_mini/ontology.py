"""noticias_mini ontology — a complete news-graph example.

``build()`` exists so integration tests can produce *ontology-side* mutations
(wrong dim, wrong analyzer) without touching the database seed.
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


def build(dim: int = 4, metric: str = "cosine", analyzer: str = "az_pt") -> Ontology:
    return Ontology(
        types=[
            UnitType(
                "noticia",
                table="noticia",
                nature="original",
                id=StableId.of("titulo"),
                text="corpo",
                attrs=[Attr("titulo", "string"), Attr("publicado_em", "datetime")],
                vector=Vector("emb", dim, metric),
                fulltext=FullText("corpo", analyzer=analyzer, language="portuguese"),
            ),
            UnitType(
                "entidade",
                table="entidade",
                attrs=[
                    Attr("nome", "string"),
                    Attr("tipo", "string", values=["pessoa", "orgao", "organizacao"]),
                ],
            ),
            UnitType("tema", table="tema", attrs=[Attr("nome", "string")]),
            UnitType(
                "documento",
                table="documento",
                attrs=[
                    Attr("numero", "string"),
                    Attr("estado", "string", values=["tramitando", "aprovado", "rejeitado"]),
                ],
            ),
        ],
        relations=[
            Relation("fala_de", "noticia", "entidade", weight=Weight("peso")),
            Relation("sobre", "noticia", "tema"),
            Relation("cita", "noticia", "documento"),
        ],
        scopes=[Scope("entidade", via="fala_de")],
        freshness=[Freshness("noticia", "publicado_em", "30d")],
    )


ontology = build()
