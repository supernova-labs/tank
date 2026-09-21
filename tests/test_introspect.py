"""Table-driven unit tests for the DDL parsers — the most brittle part of the
package. Every DDL string below was captured verbatim from a real
``INFO FOR DB/TABLE`` response (SurrealDB 2.6.5 and 3.1.6), so these lock in
the "tolerates both spellings" claim without needing a live database.
"""

import pytest

from tank.introspect import (
    is_safe_identifier,
    normalize_type,
    parse_field_ddl,
    parse_index_ddl,
    parse_table_ddl,
)

# ---------------------------------------------------------------------- tables

TABLE_CASES = [
    (
        "DEFINE TABLE liga TYPE RELATION IN origem OUT destino SCHEMALESS PERMISSIONS NONE",
        {
            "kind": "relation",
            "in_tables": ["origem"],
            "out_tables": ["destino"],
            "schemafull": False,
        },
    ),
    (
        "DEFINE TABLE sl TYPE ANY SCHEMALESS PERMISSIONS NONE",
        {"kind": "any", "in_tables": [], "out_tables": [], "schemafull": False},
    ),
    (
        "DEFINE TABLE alvo TYPE NORMAL SCHEMAFULL PERMISSIONS NONE",
        {"kind": "normal", "in_tables": [], "out_tables": [], "schemafull": True},
    ),
    (
        # review finding: TYPE RELATION with no IN/OUT — kind is relation but
        # both endpoint lists stay empty (nothing enforces direction)
        "DEFINE TABLE about TYPE RELATION SCHEMALESS PERMISSIONS NONE",
        {"kind": "relation", "in_tables": [], "out_tables": [], "schemafull": False},
    ),
    (
        "DEFINE TABLE reacts TYPE RELATION IN person | bot OUT post SCHEMAFULL PERMISSIONS NONE",
        {
            "kind": "relation",
            "in_tables": ["person", "bot"],
            "out_tables": ["post"],
            "schemafull": True,
        },
    ),
]


@pytest.mark.parametrize(("raw", "expected"), TABLE_CASES)
def test_parse_table_ddl(raw, expected):
    ddl = parse_table_ddl("t", raw)
    for key, value in expected.items():
        assert getattr(ddl, key) == value, f"{key} in {raw!r}"


# ---------------------------------------------------------------------- fields

FIELD_CASES = [
    # v3 normalizes option<T> to none | T — both must compare equal
    ("DEFINE FIELD emb ON alvo TYPE none | array<float> PERMISSIONS FULL", "array<float>|none"),
    ("DEFINE FIELD emb ON alvo TYPE option<array<float>> PERMISSIONS FULL", "array<float>|none"),
    ("DEFINE FIELD in ON liga TYPE record<origem> PERMISSIONS FULL", "record<origem>"),
    (
        "DEFINE FIELD status ON t TYPE string ASSERT $value IN ['a', 'b'] PERMISSIONS FULL",
        "string",
    ),
    ("DEFINE FIELD created ON t TYPE datetime DEFAULT time::now() PERMISSIONS FULL", "datetime"),
]


@pytest.mark.parametrize(("raw", "expected_type"), FIELD_CASES)
def test_parse_field_ddl(raw, expected_type):
    assert parse_field_ddl("f", raw).type == expected_type


def test_normalize_type_union_order_is_irrelevant():
    assert normalize_type("none | string") == normalize_type("string | none")
    assert normalize_type("option<string>") == normalize_type("none | string")


# --------------------------------------------------------------------- indexes

INDEX_CASES = [
    (
        # v3 HNSW with auto-appended suffixes (TYPE/EFC/M/M0/LM)
        (
            "DEFINE INDEX idx_vec ON alvo FIELDS emb HNSW DIMENSION 4 DIST COSINE TYPE F32 "
            "EFC 150 M 12 M0 24 LM 0.40242960438184466f"
        ),
        {"kind": "hnsw", "fields": ["emb"], "dimension": 4, "dist": "cosine"},
    ),
    (
        # v2 MTREE with CAPACITY and cache suffixes
        (
            "DEFINE INDEX idx_vec ON alvo FIELDS emb MTREE DIMENSION 4 DIST COSINE TYPE F64 "
            "CAPACITY 40 DOC_IDS_ORDER 100 DOC_IDS_CACHE 100 MTREE_CACHE 100"
        ),
        {"kind": "mtree", "fields": ["emb"], "dimension": 4, "dist": "cosine"},
    ),
    (
        # v3 fulltext spelling
        "DEFINE INDEX idx_fts ON alvo FIELDS texto FULLTEXT ANALYZER az BM25(1.2,0.75) HIGHLIGHTS",
        {"kind": "fulltext", "fields": ["texto"], "analyzer": "az"},
    ),
    (
        # v2 fulltext spelling, with the full ORDER/CACHE suffix train
        (
            "DEFINE INDEX idx_fts ON alvo FIELDS texto SEARCH ANALYZER az BM25(1.2,0.75) "
            "DOC_IDS_ORDER 100 DOC_LENGTHS_ORDER 100 POSTINGS_ORDER 100 TERMS_ORDER 100 "
            "DOC_IDS_CACHE 100 DOC_LENGTHS_CACHE 100 POSTINGS_CACHE 100 TERMS_CACHE 100 HIGHLIGHTS"
        ),
        {"kind": "fulltext", "fields": ["texto"], "analyzer": "az"},
    ),
    (
        "DEFINE INDEX idx_uni ON alvo FIELDS nome UNIQUE",
        {"kind": "unique", "fields": ["nome"]},
    ),
    (
        # HNSW default distance is EUCLIDEAN when DIST is absent
        "DEFINE INDEX idx_vec ON alvo FIELDS emb HNSW DIMENSION 8",
        {"kind": "hnsw", "dimension": 8, "dist": "euclidean"},
    ),
    (
        "DEFINE INDEX idx_multi ON alvo COLUMNS nome, kind UNIQUE",
        {"kind": "unique", "fields": ["nome", "kind"]},
    ),
]


@pytest.mark.parametrize(("raw", "expected"), INDEX_CASES)
def test_parse_index_ddl(raw, expected):
    ddl = parse_index_ddl("i", raw)
    for key, value in expected.items():
        assert getattr(ddl, key) == value, f"{key} in {raw!r}"


# ----------------------------------------------------------------- identifiers


@pytest.mark.parametrize("name", ["news", "technical_assessment", "_x", "Field9"])
def test_safe_identifiers(name):
    assert is_safe_identifier(name)


@pytest.mark.parametrize("name", ["", "9x", "a-b", "a b", "a;DROP", "tabela`"])
def test_unsafe_identifiers(name):
    assert not is_safe_identifier(name)
