# `tank check` — check reference

Every finding in the report carries a **stable code** (this page) and a **state**. A report is only valid for the environment named in its header (server, version, `ns`/`db`).

## The states

| State | Meaning |
|---|---|
| `PASS` | The declaration is **not contradicted** by the schema and the sampled data of this environment. Not a proof of semantic correctness — see the report's "not verified" section. |
| `FAIL` | The database contradicts the declaration. Breaks the build (exit 1). |
| `WARN` | Suspicious or fragile, but not contradictory. Does not break the build — unless `--strict`. |
| `VACUOUS` | A sampling check could prove nothing because **there is no data to sample** (empty table, or no row carries the sampled field). Never converted into a silent PASS — absence of data is not evidence. `--strict` treats it as a failure. |
| `INFO` | Informational, no verdict. |

**CLI exit codes**: `0` = no FAIL · `1` = FAIL findings (or WARN/VACUOUS with `--strict`) · `2` = usage error, connection error, or an **internally invalid ontology** (the `ONT-*` codes below — also any pydantic/import error while loading the ontology module).

---

## `ONT-*` — internal consistency of the ontology (static, no database)

These run **in the `Ontology` constructor**, on any import. Failure = `OntologyError` carrying **every** violation at once — the build breaks before a connection exists. Shape errors on a single field (unknown metric, `dim=0`, `values=[]`, `field_link` without `field`) surface as pydantic `ValidationError`s pointing at the exact line.

| Code | What it verifies | How to fix |
|---|---|---|
| `ONT-001` | Unique names across types, relations and scopes | Rename the duplicate |
| `ONT-002` | `Relation.from_`/`to` reference declared types (`to` may list several) | Declare the missing type or fix the name |
| `ONT-003` | `Scope.via` references a declared relation | Declare the relation or fix the name |
| `ONT-005` | No duplicate attrs within a type | Remove the duplicate |
| `ONT-008` | `Freshness.unit_type` references a declared type | Fix the type name |
| `ONT-009` | A `field_link` field does not collide with a non-record attr on the source type | Make the attr `record`, or rename |

## `TBL-*` / `VAC-*` / `CHK-*` — tables and check integrity

| Code | What it verifies | Possible states |
|---|---|---|
| `TBL-000` | The table name is a plain identifier (`[A-Za-z_][A-Za-z0-9_]*`) | FAIL |
| `TBL-001` | **The table declared in `UnitType.table` exists in the database.** The canonical error: "you are giving me an ontology that does not exist in the database". The PASS message reports `SCHEMAFULL/SCHEMALESS` and the table `kind` | PASS / FAIL |
| `VAC-001` | A declared type's table has **0 rows** → every sampling check for that type is vacuous | VACUOUS |
| `CHK-000` | A check crashed with an unexpected exception. The error is recorded as a finding and the remaining checks keep running — one flaky parse never hides the rest of the report | FAIL |

## `FLD-*` / `ATTR-*` — fields and vocabularies

The real dichotomy is **per field** (verified behavior on SurrealDB 2.x and 3.x): a field with a `DEFINE FIELD` is validated structurally — and SurrealDB itself enforces it on write, even on SCHEMALESS tables. A field without one is defended by nobody → sampling only.

| Code | What it verifies | Possible states |
|---|---|---|
| `FLD-000` | Field name is a plain identifier (applies to attrs, weight fields and link fields alike) | FAIL |
| `FLD-001` | A field referenced by the declaration (`text`, `attrs`, `locator`, `id`, `vector.field`, `fulltext.field`) has a `DEFINE FIELD` on the table; for attrs, the DDL type is compatible with the declared one | PASS |
| `FLD-002` | A field **without** a `DEFINE FIELD`: presence verified by sampling. Absent from 100% of the sample = FAIL; partial = WARN; present everywhere = PASS with a recommendation to add the `DEFINE` | PASS / WARN / FAIL |
| `FLD-003` | The `Attr` declared type diverges from the DDL type (e.g. attr `string`, DDL `int`) | WARN |
| `ATTR-010` | Sampled values of the field fit the declared `Attr.values` vocabulary | PASS / WARN |

## `REL-*` — relations

| Code | What it verifies | Possible states |
|---|---|---|
| `REL-001` | **The edge table exists** ("relation declares table X, which does not exist in the database") | implicit PASS via REL-002 / FAIL |
| `REL-002` | Edge direction. With `TYPE RELATION IN/OUT`: structural comparison — and the server **enforces direction on write**. Without an IN/OUT constraint (`TYPE ANY` implicit edges, or `TYPE RELATION` declared with no `IN`/`OUT` clause — nothing enforces direction in either case): endpoint sampling via `record::tb(in/out)` — right endpoints = WARN recommending an explicit `TYPE RELATION IN x OUT y`; wrong = FAIL; empty = VACUOUS. A relation with several targets (`dst=Source \| Note`) requires every declared target in `OUT` | PASS / WARN / FAIL / VACUOUS |
| `REL-003` | `field_link`: the field on the source type exists and is `record<target-table>` — with several targets (`Link[Source, "Note"]`), the DDL must admit every declared one (`record<source \| note>`) | PASS / WARN / FAIL / VACUOUS |
| `REL-004` | The `Weight` field exists on the edge (DEFINE or sampling) | PASS / WARN / FAIL / VACUOUS |

## `VEC-*` — vector search

The ontology declares the *capability* (`Vector(field, dim, metric)`); the index is **derived** from the declaration — never declared directly. Note the deliberate, reversible 0.1 bet: the ANN index and the embedding column are required to live *in the consumer's own table*; a future Tank-owned index projection would move these checks' target (this is listed in the report's "not verified" section).

| Code | What it verifies | Possible states |
|---|---|---|
| `VEC-001` | An ANN index (HNSW/MTREE/DISKANN) covers the declared field. Without one, vector search is a full scan or an error | implicit PASS / FAIL |
| `VEC-002` | Index `DIMENSION` == declared `dim` | PASS / FAIL |
| `VEC-003` | Index `DIST` == declared `metric` | PASS / FAIL |
| `VEC-004` | Index is MTREE — deprecated in 2.x, removed in 3.x | WARN |
| `VEC-010` | Dimension of **sampled** embeddings == `dim`. Catches rows ingested *before* the index existed (with an index present the server rejects wrong dimensions on write; without one, mixed dimensions accumulate silently — a real production failure mode). If rows exist but none carries an embedding, the state is VACUOUS — a vector-searchable type with zero vectors never prints a clean report | PASS / FAIL / VACUOUS |

## `FTS-*` — full-text search

| Code | What it verifies | Possible states |
|---|---|---|
| `FTS-001` | An FTS index (`FULLTEXT ANALYZER` on 3.x / `SEARCH ANALYZER` on 2.x) covers the declared field | PASS / FAIL |
| `FTS-002` | The index analyzer is the declared one, and is defined in the database | FAIL |
| `FTS-003` | The declared `language` is covered by the analyzer's `snowball(...)` | WARN |

## `FRS-*` — freshness

| Code | What it verifies | Possible states |
|---|---|---|
| `FRS-001` | The `Freshness` field is among the type's declared fields (and therefore validated by the FLD checks) | PASS / WARN |

---

## What `tank check` deliberately does NOT verify

Printed in every report, the honesty list: semantics of names; the real identity of the embedding model (only the declared label in 0.1); content quality/completeness; search/ranking behavior (no access queries are executed); the *semantic* direction of relations (structure ≠ meaning); sampling coverage (samples read the first N rows, and an explicit `null` counts as present); declared-but-inert constructs (`nature`, `StableId.version_fields` — recorded, not yet consumed by any check); and the index-location bet described under `VEC-*`. A validator that stays silent about its blind spots manufactures false confidence.
