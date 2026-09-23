"""`tank check`: does the database respect what the ontology declares?

Deterministic, LLM-free. Validates the *client's* tables. Check design notes,
grounded in behavior verified against SurrealDB 2.6.5 and 3.1.6:

- The real dichotomy is per-field — "has DEFINE FIELD" (structural, and the
  server already enforces it on write) vs "has none" (sampling only) — not
  schemafull vs schemaless.
- Relations: the server materializes ``in``/``out`` fields from ``TYPE RELATION
  IN a OUT b`` and enforces direction itself — so REL checks read those fields;
  ``TYPE ANY`` edges (implicit RELATE tables) fall back to sampling.
- With an ANN index present the server rejects wrong-dimension writes, so the
  dimension sampling (VEC-010) exists to catch rows ingested *before* the
  index existed — a real production failure mode.
- An empty table proves nothing: sampling checks report VACUOUS, never PASS.
"""

from __future__ import annotations

import re

from tank.introspect import DbInfo, Introspector, TableInfo, is_safe_identifier
from tank.ontology import Ontology, Relation, UnitType
from tank.report import Report

# Attr.type -> acceptable normalized SurrealQL types (beyond the exact match)
_TYPE_COMPAT: dict[str, set[str]] = {
    "string": {"string"},
    "int": {"int", "number"},
    "float": {"float", "number"},
    "number": {"number", "int", "float", "decimal"},
    "bool": {"bool"},
    "datetime": {"datetime"},
    "duration": {"duration"},
    "record": set(),  # any record<...> accepted, matched by prefix below
    "array": set(),  # any array<...>
    "object": {"object"},
}

_ANN_KINDS = ("hnsw", "mtree", "diskann")


async def run_check(
    ontology: Ontology,
    url: str,
    namespace: str,
    database: str,
    user: str = "root",
    password: str = "root",
) -> Report:
    async with Introspector(url, namespace, database, user, password) as intro:
        report = Report(
            server_url=url,
            server_version=intro.server_version(),
            namespace=namespace,
            database=database,
        )
        db = await intro.db_info()

        for unit_type in ontology.types:
            try:
                await _check_unit_type(intro, db, unit_type, report)
            except Exception as exc:  # noqa: BLE001 - one crashed check must not hide the rest
                report.add(
                    "CHK-000",
                    "FAIL",
                    f"type:{unit_type.name}",
                    f"check crashed: {exc!r} — remaining checks continued",
                )
        for relation in ontology.relations:
            try:
                await _check_relation(intro, db, ontology, relation, report)
            except Exception as exc:  # noqa: BLE001
                report.add(
                    "CHK-000",
                    "FAIL",
                    f"relation:{relation.name}",
                    f"check crashed: {exc!r} — remaining checks continued",
                )
        for fresh in ontology.freshness:
            _check_freshness_static(ontology, fresh, report)

    return report


# ------------------------------------------------------------------ unit types


async def _check_unit_type(
    intro: Introspector, db: DbInfo, unit_type: UnitType, report: Report
) -> None:
    subject = f"type:{unit_type.name}"
    table = unit_type.table

    if not is_safe_identifier(table):
        report.add("TBL-000", "FAIL", subject, f"table name {table!r} is not a plain identifier")
        return

    # TBL-001 — the declared table exists
    if table not in db.tables:
        report.add(
            "TBL-001",
            "FAIL",
            subject,
            f"type {unit_type.name!r} declares table {table!r}, which does not exist "
            f"in the database",
            table=table,
        )
        return
    table_ddl = db.tables[table]
    report.add(
        "TBL-001",
        "PASS",
        subject,
        f"table {table!r} exists "
        f"({'SCHEMAFULL' if table_ddl.schemafull else 'SCHEMALESS'}, kind={table_ddl.kind})",
        table=table,
    )

    info = await intro.table_info(table)
    total = await intro.count(table)
    report.table_counts[table] = total

    # VAC-001 — empty table: sampling checks below are vacuous
    if total == 0:
        report.add(
            "VAC-001",
            "VACUOUS",
            subject,
            f"table {table!r} has 0 rows — every sampling check for this type is vacuous; "
            "structural checks still apply",
            table=table,
        )

    # FLD — every field the declaration references (per-field dichotomy)
    for field_name in sorted(unit_type.declared_fields()):
        await _check_field(intro, info, unit_type, field_name, total, report)

    # ATTR-010 — declared value vocabulary matches sampled data
    for attr in unit_type.attrs:
        if attr.values and total > 0 and is_safe_identifier(attr.name):
            observed = await intro.sample_values(table, attr.name)
            unexpected = sorted({str(v) for v in observed} - set(attr.value_codes()))
            if unexpected:
                report.add(
                    "ATTR-010",
                    "WARN",
                    subject,
                    f"attr {attr.name!r}: sampled values {unexpected} are outside the "
                    f"declared vocabulary {attr.value_codes()}",
                    table=table,
                )
            else:
                report.add(
                    "ATTR-010",
                    "PASS",
                    subject,
                    f"attr {attr.name!r}: sampled values within declared vocabulary",
                    table=table,
                )

    # VEC — vector declaration ⇒ ANN index derived from it
    if unit_type.vector:
        _check_vector_index(info, unit_type, report)
        if total > 0 and is_safe_identifier(unit_type.vector.field):
            lens = {
                len(v)
                for v in await intro.sample_values(table, unit_type.vector.field, limit=500)
                if isinstance(v, list)
            }
            wrong = sorted(lens - {unit_type.vector.dim})
            if wrong:
                report.add(
                    "VEC-010",
                    "FAIL",
                    subject,
                    f"sampled embeddings in {unit_type.vector.field!r} have dimensions "
                    f"{wrong}, expected {unit_type.vector.dim} — rows ingested before the "
                    "index existed are not defended by the server",
                    table=table,
                )
            elif lens:
                report.add(
                    "VEC-010",
                    "PASS",
                    subject,
                    f"sampled embedding dimensions all match {unit_type.vector.dim}",
                    table=table,
                )
            else:
                report.add(
                    "VEC-010",
                    "VACUOUS",
                    subject,
                    f"table {table!r} has {total} rows but none carries an embedding in "
                    f"{unit_type.vector.field!r} — vector search would return nothing "
                    "(has the embedding job run?)",
                    table=table,
                )

    # FTS — fulltext declaration ⇒ FTS index + analyzer
    if unit_type.fulltext:
        _check_fulltext_index(db, info, unit_type, report)


async def _check_field(
    intro: Introspector,
    info: TableInfo,
    unit_type: UnitType,
    field_name: str,
    total: int,
    report: Report,
) -> None:
    subject = f"type:{unit_type.name}"
    table = unit_type.table
    if not is_safe_identifier(field_name):
        report.add(
            "FLD-000", "FAIL", subject, f"field name {field_name!r} is not a plain identifier"
        )
        return

    defined = info.fields.get(field_name)
    attr = next((a for a in unit_type.attrs if a.name == field_name), None)

    if defined is not None:
        # structural: DEFINE FIELD exists — the server enforces it on write
        if attr is not None and defined.type is not None:
            _check_attr_type(unit_type, attr.name, attr.type, defined.type, report)
        else:
            report.add(
                "FLD-001",
                "PASS",
                subject,
                f"field {field_name!r} is defined on {table!r}",
                table=table,
            )
        return

    # no DEFINE FIELD: nobody defends this field — sample for presence (FLD-002)
    if total == 0:
        return  # covered by VAC-001
    present, _ = await intro.field_presence(table, field_name)
    if present == 0:
        report.add(
            "FLD-002",
            "FAIL",
            subject,
            f"field {field_name!r} has no DEFINE FIELD on {table!r} and is absent from "
            "every sampled row",
            table=table,
        )
    elif present < total:
        report.add(
            "FLD-002",
            "WARN",
            subject,
            f"field {field_name!r} has no DEFINE FIELD on {table!r}; present in "
            f"{present}/{total} rows (nothing defends it on write)",
            table=table,
        )
    else:
        report.add(
            "FLD-002",
            "PASS",
            subject,
            f"field {field_name!r} present in all {total} sampled rows "
            "(no DEFINE FIELD — consider adding one so the server defends it)",
            table=table,
        )


def _check_attr_type(
    unit_type: UnitType, name: str, declared: str, actual_normalized: str, report: Report
) -> None:
    subject = f"type:{unit_type.name}"
    # strip optionality for comparison: none|T ≡ T for type compatibility
    parts = [p for p in actual_normalized.split("|") if p != "none"]
    core = parts[0] if len(parts) == 1 else actual_normalized
    compatible = (
        core in _TYPE_COMPAT.get(declared, set())
        or (declared == "record" and core.startswith("record"))
        or (declared == "array" and core.startswith("array"))
    )
    if compatible:
        report.add(
            "FLD-001",
            "PASS",
            subject,
            f"attr {name!r}: declared {declared!r} matches DEFINE FIELD type {core!r}",
            table=unit_type.table,
        )
    else:
        report.add(
            "FLD-003",
            "WARN",
            subject,
            f"attr {name!r}: declared type {declared!r} but DEFINE FIELD says {core!r}",
            table=unit_type.table,
        )


def _check_vector_index(info: TableInfo, unit_type: UnitType, report: Report) -> None:
    # Deliberate, reversible bet: 0.1 requires the ANN index (and the embedding
    # column) to live in the consumer's own table. If a Tank-owned index
    # projection lands later, VEC-*/FTS-* change target to the projection and
    # Vector.model becomes Tank config. Recorded in the report's not_verified list.
    subject = f"type:{unit_type.name}"
    vector = unit_type.vector
    assert vector is not None
    ann = [
        idx
        for idx in info.indexes.values()
        if idx.kind in _ANN_KINDS and idx.fields == [vector.field]
    ]
    if not ann:
        report.add(
            "VEC-001",
            "FAIL",
            subject,
            f"vector declared on field {vector.field!r} but no ANN index (HNSW/MTREE/DISKANN) "
            f"covers it on {unit_type.table!r} — vector search would be a full scan or an error",
            table=unit_type.table,
        )
        return
    idx = ann[0]
    if idx.kind == "mtree":
        report.add(
            "VEC-004",
            "WARN",
            subject,
            f"index {idx.name!r} is MTREE — deprecated in 2.x, removed in 3.x "
            "(auto-converted to HNSW on migration)",
            table=unit_type.table,
        )
    if idx.dimension != vector.dim:
        report.add(
            "VEC-002",
            "FAIL",
            subject,
            f"index {idx.name!r} has DIMENSION {idx.dimension}, ontology declares dim={vector.dim}",
            table=unit_type.table,
        )
    else:
        report.add(
            "VEC-002",
            "PASS",
            subject,
            f"index {idx.name!r} DIMENSION matches ({vector.dim})",
            table=unit_type.table,
        )
    if idx.dist != vector.metric:
        report.add(
            "VEC-003",
            "FAIL",
            subject,
            f"index {idx.name!r} has DIST {idx.dist!r}, ontology declares metric={vector.metric!r}",
            table=unit_type.table,
        )
    else:
        report.add(
            "VEC-003",
            "PASS",
            subject,
            f"index {idx.name!r} DIST matches ({vector.metric})",
            table=unit_type.table,
        )


def _check_fulltext_index(db: DbInfo, info: TableInfo, unit_type: UnitType, report: Report) -> None:
    subject = f"type:{unit_type.name}"
    fulltext = unit_type.fulltext
    assert fulltext is not None
    fts = [
        idx
        for idx in info.indexes.values()
        if idx.kind == "fulltext" and idx.fields == [fulltext.field]
    ]
    if not fts:
        report.add(
            "FTS-001",
            "FAIL",
            subject,
            f"fulltext declared on field {fulltext.field!r} but no FTS index covers it on "
            f"{unit_type.table!r} (a match operator would error, a CONTAINS would full-scan)",
            table=unit_type.table,
        )
        return
    idx = fts[0]
    report.add(
        "FTS-001",
        "PASS",
        subject,
        f"FTS index {idx.name!r} covers {fulltext.field!r} (analyzer: {idx.analyzer})",
        table=unit_type.table,
    )
    if fulltext.analyzer and idx.analyzer != fulltext.analyzer:
        report.add(
            "FTS-002",
            "FAIL",
            subject,
            f"declared analyzer {fulltext.analyzer!r} but index uses {idx.analyzer!r}",
            table=unit_type.table,
        )
    if idx.analyzer and idx.analyzer not in db.analyzers:
        report.add(
            "FTS-002",
            "FAIL",
            subject,
            f"index analyzer {idx.analyzer!r} is not defined in the database",
            table=unit_type.table,
        )
    if fulltext.language and idx.analyzer and idx.analyzer in db.analyzers:
        analyzer_ddl = db.analyzers[idx.analyzer].lower()
        if f"snowball({fulltext.language.lower()})" not in analyzer_ddl:
            report.add(
                "FTS-003",
                "WARN",
                subject,
                f"declared language {fulltext.language!r} but analyzer {idx.analyzer!r} does "
                f"not stem it (DDL: {db.analyzers[idx.analyzer]})",
                table=unit_type.table,
            )


# ------------------------------------------------------------------- relations


async def _check_relation(
    intro: Introspector, db: DbInfo, ontology: Ontology, relation: Relation, report: Report
) -> None:
    subject = f"relation:{relation.name}"
    from_table = ontology.type_named(relation.from_).table
    to_tables = [ontology.type_named(t).table for t in relation.targets()]
    to_spec = " | ".join(to_tables)  # SurrealQL spelling of several OUT tables

    if relation.kind == "field_link":
        await _check_field_link(intro, db, relation, from_table, to_tables, report)
        return

    edge_table = relation.table or relation.name
    if edge_table not in db.tables:
        report.add(
            "REL-001",
            "FAIL",
            subject,
            f"relation {relation.name!r} declares edge table {edge_table!r}, which does not "
            "exist in the database",
            table=edge_table,
        )
        return
    table_ddl = db.tables[edge_table]
    info = await intro.table_info(edge_table)
    count = await intro.count(edge_table)
    report.table_counts[edge_table] = count

    if table_ddl.kind == "relation" and (table_ddl.in_tables or table_ddl.out_tables):
        # strong path: TYPE RELATION IN/OUT — server enforces direction itself
        problems = []
        if table_ddl.in_tables and from_table not in table_ddl.in_tables:
            problems.append(f"IN is {table_ddl.in_tables}, expected {from_table!r}")
        missing_out = [t for t in to_tables if t not in table_ddl.out_tables]
        if table_ddl.out_tables and missing_out:
            problems.append(f"OUT is {table_ddl.out_tables}, missing {missing_out}")
        if problems:
            report.add(
                "REL-002",
                "FAIL",
                subject,
                f"edge {edge_table!r} direction contradicts the ontology: "
                + "; ".join(problems)
                + f" (declared {relation.from_} -> {' | '.join(relation.targets())})",
                table=edge_table,
            )
        else:
            report.add(
                "REL-002",
                "PASS",
                subject,
                f"edge {edge_table!r} is TYPE RELATION {from_table} -> {to_spec}; the server "
                "enforces direction on write",
                table=edge_table,
            )
    elif table_ddl.kind in ("any", "relation"):
        # weak path: TYPE ANY (implicit RELATE table) or TYPE RELATION without
        # IN/OUT — in both cases nothing enforces direction on write, so sample
        if count == 0:
            report.add(
                "REL-002",
                "VACUOUS",
                subject,
                f"edge {edge_table!r} has no IN/OUT constraint "
                f"({'TYPE RELATION without IN/OUT' if table_ddl.kind == 'relation' else 'TYPE ANY'}) "
                "and is empty — direction cannot be verified; recommend "
                f"DEFINE TABLE {edge_table} TYPE RELATION IN {from_table} OUT {to_spec}",
                table=edge_table,
            )
        else:
            pairs = set(await intro.edge_endpoint_tables(edge_table))
            bad = {p for p in pairs if p[0] != from_table or p[1] not in to_tables}
            if bad:
                report.add(
                    "REL-002",
                    "FAIL",
                    subject,
                    f"edge {edge_table!r} (no IN/OUT constraint) has sampled endpoints "
                    f"{sorted(bad)}, expected ({from_table!r}, {to_spec!r})",
                    table=edge_table,
                )
            else:
                report.add(
                    "REL-002",
                    "WARN",
                    subject,
                    f"edge {edge_table!r} endpoints match by sampling, but it has no "
                    "IN/OUT constraint — nothing defends direction on write; recommend "
                    f"DEFINE TABLE {edge_table} TYPE RELATION IN {from_table} OUT {to_spec}",
                    table=edge_table,
                )
    else:
        report.add(
            "REL-002",
            "FAIL",
            subject,
            f"table {edge_table!r} exists but is TYPE NORMAL — not usable as a graph edge "
            "(RELATE requires a relation or implicit table)",
            table=edge_table,
        )

    # weight field on the edge (per-field dichotomy again)
    if relation.weight:
        weight_field = relation.weight.field
        if not is_safe_identifier(weight_field):
            report.add(
                "FLD-000",
                "FAIL",
                subject,
                f"weight field name {weight_field!r} is not a plain identifier",
                table=edge_table,
            )
            return
        if weight_field in info.fields:
            report.add(
                "REL-004",
                "PASS",
                subject,
                f"weight field {weight_field!r} is defined on edge {edge_table!r}",
                table=edge_table,
            )
        elif count == 0:
            report.add(
                "REL-004",
                "VACUOUS",
                subject,
                f"weight field {weight_field!r} has no DEFINE and the edge is empty",
                table=edge_table,
            )
        else:
            present, total = await intro.field_presence(edge_table, weight_field)
            if present == 0:
                report.add(
                    "REL-004",
                    "FAIL",
                    subject,
                    f"weight field {weight_field!r} absent from every sampled edge row",
                    table=edge_table,
                )
            else:
                report.add(
                    "REL-004",
                    "PASS" if present == total else "WARN",
                    subject,
                    f"weight field {weight_field!r} present in {present}/{total} sampled rows "
                    "(no DEFINE FIELD)",
                    table=edge_table,
                )


async def _check_field_link(
    intro: Introspector,
    db: DbInfo,
    relation: Relation,
    from_table: str,
    to_tables: list[str],
    report: Report,
) -> None:
    subject = f"relation:{relation.name}"
    expected = f"record<{'|'.join(to_tables)}>"
    link_field = relation.field
    assert link_field is not None
    if not is_safe_identifier(link_field):
        report.add(
            "FLD-000",
            "FAIL",
            subject,
            f"field_link field name {link_field!r} is not a plain identifier",
            table=from_table,
        )
        return
    if from_table not in db.tables:
        return  # TBL-001 on the owning type already failed
    info = await intro.table_info(from_table)
    defined = info.fields.get(link_field)
    if defined is None:
        count = await intro.count(from_table)
        if count == 0:
            report.add(
                "REL-003",
                "VACUOUS",
                subject,
                f"field_link {link_field!r} has no DEFINE FIELD on {from_table!r} and the "
                "table is empty",
                table=from_table,
            )
            return
        present, total = await intro.field_presence(from_table, link_field)
        status = "FAIL" if present == 0 else "WARN"
        report.add(
            "REL-003",
            status,
            subject,
            f"field_link {link_field!r} has no DEFINE FIELD on {from_table!r}; present in "
            f"{present}/{total} sampled rows",
            table=from_table,
        )
        return
    actual_targets = _record_targets(defined.type)
    # Equality, not containment. A column that accepts MORE tables than the
    # declaration names is not slack, it is a contract the agent cannot see: the
    # declaration is what an agent reads to decide what a traversal returns, so
    # an undeclared target is a row it will mishandle. The message prints the
    # type that was OBSERVED, never the one derived from the declaration —
    # otherwise a PASS asserts the shape it was looking for rather than the one
    # it found.
    if actual_targets is not None and actual_targets == set(to_tables):
        report.add(
            "REL-003",
            "PASS",
            subject,
            f"field_link {link_field!r} on {from_table!r} is {defined.type!r}",
            table=from_table,
        )
    elif actual_targets is not None and set(to_tables) < actual_targets:
        report.add(
            "REL-003",
            "FAIL",
            subject,
            f"field_link {link_field!r} on {from_table!r} is {defined.type!r}, which accepts "
            f"{sorted(actual_targets - set(to_tables))} on top of the declared {expected} — "
            "declare every target the column can hold, or narrow the column",
            table=from_table,
        )
    elif actual_targets is not None:
        report.add(
            "REL-003",
            "FAIL",
            subject,
            f"field_link {link_field!r} on {from_table!r} is {defined.type!r}, expected {expected}",
            table=from_table,
        )
    else:
        report.add(
            "REL-003",
            "FAIL",
            subject,
            f"field_link {link_field!r} on {from_table!r} is {defined.type!r} — not a record "
            "link at all",
            table=from_table,
        )


_RECORD_RE = re.compile(r"record<([^>]*)>")


def _record_targets(normalized_type: str | None) -> set[str] | None:
    """``none|record<a|b>`` -> ``{"a", "b"}``; ``None`` when the type is not a record link."""
    if not normalized_type:
        return None
    match = _RECORD_RE.search(normalized_type)
    if not match:
        return None
    return {t.strip() for t in match.group(1).split("|") if t.strip()}


# ------------------------------------------------------------------- freshness


def _check_freshness_static(ontology: Ontology, fresh: object, report: Report) -> None:
    # the field itself is validated by the FLD checks of the owning type; here we
    # only confirm the declaration points at a declared field
    from tank.ontology import Freshness

    assert isinstance(fresh, Freshness)
    unit_type = ontology.type_named(fresh.unit_type)
    subject = f"freshness:{fresh.unit_type}"
    if fresh.field not in unit_type.declared_fields():
        report.add(
            "FRS-001",
            "WARN",
            subject,
            f"freshness field {fresh.field!r} is not among the declared fields of "
            f"{fresh.unit_type!r} — declare it as an attr (type datetime) so it is validated",
        )
    else:
        report.add("FRS-001", "PASS", subject, f"freshness field {fresh.field!r} is declared")
