"""Read what the database actually is: INFO FOR DB/TABLE plus defensive DDL parsing.

SurrealDB returns DDL as *strings* (the structured variant is documented as
"internal use, subject to change"), so the stable contract is parsing the
normalized DDL. Behavior below was verified empirically against SurrealDB
2.6.5 and 3.1.6:

- The key set of ``INFO FOR DB`` varies per version → read what we know,
  ignore the rest.
- Index DDL carries auto-appended suffixes (``TYPE F32 EFC 150 M 12 M0 24
  LM 0.40…`` on v3 HNSW; ``CAPACITY 40 DOC_IDS_ORDER 100 …`` on v2 MTREE) →
  extract what we need, tolerate the rest.
- ``TYPE RELATION IN a OUT b`` is the DDL spelling (not FROM/TO), and the
  server materializes ``DEFINE FIELD in/out TYPE record<…>`` automatically.
- A table created implicitly by RELATE shows up as ``TYPE ANY SCHEMALESS``.
- v3 normalizes ``option<T>`` to ``none | T`` → both spellings compare equal.
- v2 spells full-text indexes ``SEARCH ANALYZER``; v3 spells them ``FULLTEXT
  ANALYZER`` — one index kind here.
"""

from __future__ import annotations

import re
import urllib.request
from dataclasses import dataclass, field

from surrealdb import AsyncSurreal

IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def is_safe_identifier(name: str) -> bool:
    """Only plain identifiers are interpolated into sampling queries."""
    return bool(IDENT_RE.match(name))


# --------------------------------------------------------------------------- DDL


@dataclass
class TableDDL:
    name: str
    raw: str
    kind: str = "normal"  # normal | any | relation
    in_tables: list[str] = field(default_factory=list)
    out_tables: list[str] = field(default_factory=list)
    schemafull: bool = False


@dataclass
class FieldDDL:
    name: str
    raw: str
    type: str | None = None  # normalized, e.g. "string", "none|array<float>", "record<origem>"


@dataclass
class IndexDDL:
    name: str
    raw: str
    fields: list[str] = field(default_factory=list)
    kind: str = "plain"  # plain | unique | fulltext | hnsw | mtree | diskann
    dimension: int | None = None
    dist: str | None = None
    analyzer: str | None = None


@dataclass
class TableInfo:
    fields: dict[str, FieldDDL]
    indexes: dict[str, IndexDDL]


@dataclass
class DbInfo:
    tables: dict[str, TableDDL]
    analyzers: dict[str, str]


_TABLE_RELATION_RE = re.compile(
    r"\bTYPE\s+RELATION\b(?:\s+IN\s+(?P<in>[\w|`\s]+?)\s+OUT\s+(?P<out>[\w|`\s]+?))?"
    r"(?=\s+(?:SCHEMAFULL|SCHEMALESS|PERMISSIONS|ENFORCED|COMMENT|CHANGEFEED|AS)\b|\s*$)"
)


def parse_table_ddl(name: str, raw: str) -> TableDDL:
    ddl = TableDDL(name=name, raw=raw)
    ddl.schemafull = " SCHEMAFULL" in raw
    if re.search(r"\bTYPE\s+ANY\b", raw):
        ddl.kind = "any"
    match = _TABLE_RELATION_RE.search(raw)
    if match:
        ddl.kind = "relation"
        if match.group("in"):
            ddl.in_tables = [t.strip(" `") for t in match.group("in").split("|")]
        if match.group("out"):
            ddl.out_tables = [t.strip(" `") for t in match.group("out").split("|")]
    return ddl


_FIELD_TYPE_RE = re.compile(
    r"\bTYPE\s+(?P<type>.+?)(?=\s+(?:DEFAULT|VALUE|ASSERT|PERMISSIONS|READONLY|COMMENT|REFERENCE)\b|\s*$)"
)


def normalize_type(type_str: str) -> str:
    """Normalize a SurrealQL type so v2/v3 spellings compare equal.

    ``option<T>`` ≡ ``none | T``; whitespace and case are irrelevant; union
    member order is irrelevant.
    """
    t = type_str.strip().lower().replace(" ", "")
    option = re.fullmatch(r"option<(.+)>", t)
    if option:
        t = f"none|{option.group(1)}"
    if "|" in t and "<" not in t.split("|", 1)[0]:
        # sort top-level union members (none | string == string | none)
        parts = _split_top_level_union(t)
        t = "|".join(sorted(parts))
    return t


def _split_top_level_union(t: str) -> list[str]:
    parts, depth, current = [], 0, ""
    for ch in t:
        if ch == "<":
            depth += 1
        elif ch == ">":
            depth -= 1
        if ch == "|" and depth == 0:
            parts.append(current)
            current = ""
        else:
            current += ch
    parts.append(current)
    return [p for p in parts if p]


def parse_field_ddl(name: str, raw: str) -> FieldDDL:
    ddl = FieldDDL(name=name, raw=raw)
    match = _FIELD_TYPE_RE.search(raw)
    if match:
        ddl.type = normalize_type(match.group("type"))
    return ddl


_INDEX_FIELDS_RE = re.compile(
    r"\b(?:FIELDS|COLUMNS)\s+(?P<fields>.+?)(?=\s+(?:UNIQUE|FULLTEXT|SEARCH|HNSW|MTREE|DISKANN|COMMENT|CONCURRENTLY)\b|\s*$)"
)
_INDEX_DIM_RE = re.compile(r"\bDIMENSION\s+(\d+)")
_INDEX_DIST_RE = re.compile(r"\bDIST\s+(\w+)")
_INDEX_ANALYZER_RE = re.compile(r"\b(?:FULLTEXT|SEARCH)\s+ANALYZER\s+(\w+)")


def parse_index_ddl(name: str, raw: str) -> IndexDDL:
    ddl = IndexDDL(name=name, raw=raw)
    match = _INDEX_FIELDS_RE.search(raw)
    if match:
        ddl.fields = [f.strip(" `") for f in match.group("fields").split(",")]
    if re.search(r"\bUNIQUE\b", raw):
        ddl.kind = "unique"
    elif re.search(r"\b(?:FULLTEXT|SEARCH)\s+ANALYZER\b", raw):
        ddl.kind = "fulltext"
        analyzer_match = _INDEX_ANALYZER_RE.search(raw)
        ddl.analyzer = analyzer_match.group(1) if analyzer_match else None
    elif re.search(r"\bHNSW\b", raw):
        ddl.kind = "hnsw"
    elif re.search(r"\bMTREE\b", raw):
        ddl.kind = "mtree"
    elif re.search(r"\bDISKANN\b", raw):
        ddl.kind = "diskann"
    if ddl.kind in ("hnsw", "mtree", "diskann"):
        dim_match = _INDEX_DIM_RE.search(raw)
        ddl.dimension = int(dim_match.group(1)) if dim_match else None
        dist_match = _INDEX_DIST_RE.search(raw)
        # HNSW/MTREE default distance is EUCLIDEAN when DIST is absent
        ddl.dist = (dist_match.group(1) if dist_match else "EUCLIDEAN").lower()
    return ddl


# ---------------------------------------------------------------------- client


class Introspector:
    """Thin async wrapper over the official SDK (signin → use → query)."""

    def __init__(self, url: str, namespace: str, database: str, user: str, password: str):
        self.url = url
        self.namespace = namespace
        self.database = database
        self._user = user
        self._password = password
        self._db: AsyncSurreal | None = None

    async def __aenter__(self) -> Introspector:  # noqa: PYI034 - py3.11 has no typing.Self
        self._db = AsyncSurreal(self.url)
        await self._db.signin({"username": self._user, "password": self._password})
        await self._db.use(self.namespace, self.database)
        return self

    async def __aexit__(self, *exc: object) -> None:
        if self._db is not None:
            try:
                await self._db.close()
            except Exception:  # noqa: BLE001, S110 - SDK http connections have no close()
                pass

    async def query(self, statement: str) -> object:
        assert self._db is not None, "use `async with Introspector(...)`"
        result = await self._db.query(statement)
        if isinstance(result, str):  # SDK signals statement errors as strings
            raise RuntimeError(result)  # noqa: TRY004 - a server-side error, not a type error
        return result

    def server_version(self) -> str | None:
        """GET /version on the HTTP endpoint (canonical source of the server version)."""
        base = self.url.replace("ws://", "http://").replace("wss://", "https://")
        base = base.removesuffix("/rpc")
        try:
            with urllib.request.urlopen(f"{base}/version", timeout=5) as response:
                return response.read().decode().strip()
        except Exception:  # noqa: BLE001 - version is best-effort header info
            return None

    async def db_info(self) -> DbInfo:
        raw = await self.query("INFO FOR DB;")
        tables_raw = raw.get("tables", {}) if isinstance(raw, dict) else {}
        analyzers = raw.get("analyzers", {}) if isinstance(raw, dict) else {}
        tables = {
            name: parse_table_ddl(name, ddl if isinstance(ddl, str) else str(ddl.get("sql", ddl)))
            for name, ddl in tables_raw.items()
        }
        return DbInfo(tables=tables, analyzers=dict(analyzers))

    async def table_info(self, table: str) -> TableInfo:
        raw = await self.query(f"INFO FOR TABLE `{table}`;")
        fields_raw = raw.get("fields", {}) if isinstance(raw, dict) else {}
        indexes_raw = raw.get("indexes", {}) if isinstance(raw, dict) else {}
        fields = {
            name: parse_field_ddl(name, ddl if isinstance(ddl, str) else str(ddl.get("sql", ddl)))
            for name, ddl in fields_raw.items()
        }
        indexes = {
            name: parse_index_ddl(name, ddl if isinstance(ddl, str) else str(ddl.get("sql", ddl)))
            for name, ddl in indexes_raw.items()
        }
        return TableInfo(fields=fields, indexes=indexes)

    async def count(self, table: str) -> int:
        result = await self.query(f"SELECT count() AS n FROM `{table}` GROUP ALL;")
        if isinstance(result, list) and result:
            return int(result[0].get("n", 0))
        return 0

    async def sample_values(self, table: str, field_name: str, limit: int = 200) -> list[object]:
        result = await self.query(
            f"SELECT VALUE `{field_name}` FROM `{table}` "
            f"WHERE `{field_name}` != NONE LIMIT {limit};"
        )
        return list(result) if isinstance(result, list) else []

    async def field_presence(self, table: str, field_name: str) -> tuple[int, int]:
        """(rows where field is present, total rows) — count(expr) counts truthy values."""
        result = await self.query(
            f"SELECT count(`{field_name}` != NONE) AS present, count() AS total "
            f"FROM `{table}` GROUP ALL;"
        )
        if isinstance(result, list) and result:
            row = result[0]
            return int(row.get("present", 0)), int(row.get("total", 0))
        return 0, 0

    async def edge_endpoint_tables(self, table: str, limit: int = 200) -> list[tuple[str, str]]:
        """Sampled (tb(in), tb(out)) pairs of an edge table — record::tb works on
        both 2.x and 3.x."""
        result = await self.query(
            f"SELECT record::tb(in) AS f, record::tb(out) AS t FROM `{table}` LIMIT {limit};"
        )
        if not isinstance(result, list):
            return []
        return [(str(r.get("f")), str(r.get("t"))) for r in result if isinstance(r, dict)]
