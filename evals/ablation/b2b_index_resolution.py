"""B2b — can the gateway recover WHICH FIELD an indexed query filtered on?

B2 measured plan coverage over 1,708 real agent statements and found one step of
the tier-3a matcher completely unexercised: **index → field**. Neither ablation
fixture has a single ``DEFINE INDEX``, so no ``IndexScan`` ever appeared.

That step matters because of an asymmetry in the plan: a scan prints the
predicate as text (``"predicate": "desk = 'Science'"``, field right there), but
an *indexed* lookup prints only the index name (``"index": "idx_desk"``) — the
field is gone. If the gateway cannot map the name back, then turning on an index
would make an attr stop being observable, which is the worst possible failure:
the instrument gets quieter exactly as the database gets better tuned.

This bench seeds ``tests/fixtures/news_mini`` (real FULLTEXT + HNSW), adds
standard/composite/unique indexes on top, builds the map with the repo's own
``Introspector`` + ``parse_index_ddl``, and checks every case against ground
truth — including the ones designed to break it.

    uv run python evals/ablation/b2b_index_resolution.py --port 8046
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

HERE = Path(__file__).parent
REPO = HERE.parent.parent
sys.path.insert(0, str(HERE))

import b2_plan_coverage as b2

from tank.introspect import Introspector

NS, DB = "b2b", "news_mini"
b2.NS = NS  # b2.sql() reads the namespace off the module it lives in
SEED = REPO / "tests" / "fixtures" / "news_mini" / "seed.surql"

# Indexes the fixture does not have. news_mini ships FULLTEXT + HNSW only, and
# the common production case — a plain B-tree on a filterable attr — is exactly
# the one that hides the field.
BENCH_INDEXES = """
DEFINE INDEX idx_pub      ON news     FIELDS published_at;
DEFINE INDEX idx_title    ON news     FIELDS title;
DEFINE INDEX idx_ent_kind ON entity   FIELDS kind, name;
DEFINE INDEX idx_doc_num  ON document FIELDS number UNIQUE;
"""

# (label, sql, the field the query REALLY filters on)
# The first two are the SAME query with and without the index: the cleanest
# demonstration that the field survives a scan and vanishes under an index.
CASES: list[tuple[str, str, str | None]] = [
    (
        "mesma query, SEM índice (WITH NOINDEX)",
        "SELECT id FROM news WITH NOINDEX WHERE title = 'Quantum leap'",
        "title",
    ),
    ("mesma query, COM índice", "SELECT id FROM news WHERE title = 'Quantum leap'", "title"),
    ("campo sem índice nenhum", "SELECT id FROM document WHERE status = 'approved'", "status"),
    (
        "range em campo indexado",
        "SELECT id FROM news WHERE published_at > d'2020-01-01T00:00:00Z'",
        "published_at",
    ),
    (
        "composto, prefixo completo (kind+name)",
        "SELECT id FROM entity WHERE kind = 'person' AND name = 'Ada'",
        "kind",
    ),
    ("composto, só o prefixo (kind)", "SELECT id FROM entity WHERE kind = 'person'", "kind"),
    ("composto, só o SEGUNDO campo (name)", "SELECT id FROM entity WHERE name = 'Ada'", "name"),
    ("unique", "SELECT id FROM document WHERE number = 'PL-1'", "number"),
    ("full-text", "SELECT id FROM news WHERE body @1@ 'quantum'", "body"),
    ("vetorial (KNN)", "SELECT id FROM news WHERE emb <|2,10|> [0.1,0.2,0.3,0.4]", "emb"),
    ("travessia de grafo", "SELECT id FROM mentions WHERE out = entity:e1", "out"),
]


async def index_map(url: str) -> dict[str, tuple[str, list[str], str]]:
    """{index name: (table, ordered fields, kind)} — built with the repo's own
    introspection, as the plan claims. Zero new parsing code is the claim under
    test here, not just the resolution itself."""
    out: dict[str, tuple[str, list[str], str]] = {}
    async with Introspector(url, NS, DB, "root", "root") as intro:
        db = await intro.db_info()
        for table in db.tables:
            info = await intro.table_info(table)
            for idx in info.indexes.values():
                out[idx.name] = (table, list(idx.fields), idx.kind or "standard")
    return out


def run_case(port: int, sql_text: str) -> b2.Observation:
    """EXPLAIN one statement and collect what the plan exposed."""
    out = b2.sql(port, DB, f"{sql_text} EXPLAIN;")
    obs = b2.Observation()
    if out and out[0].get("status") == "OK":
        obs.ok = True
        b2.walk(out[0].get("result"), obs)
    else:
        obs.error = str(out[0].get("result"))[:100] if out else "empty"
    return obs


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8046)
    args = parser.parse_args()
    port = args.port
    url = f"http://127.0.0.1:{port}"

    print("Subindo SurrealDB e semeando news_mini…")
    proc = b2.boot(port)
    try:
        b2.sql(port, None, f"DEFINE NAMESPACE {NS};")
        b2.sql(port, None, f"USE NS {NS}; DEFINE DATABASE {DB};")
        seeded = b2.sql(port, DB, SEED.read_text())
        bad = [r for r in seeded if r.get("status") != "OK"]
        print(f"  seed: {len(seeded)} statements, {len(bad)} failed")
        extra = b2.sql(port, DB, BENCH_INDEXES)
        print(
            f"  índices da bancada: {len(extra)} statements, "
            f"{len([r for r in extra if r.get('status') != 'OK'])} failed"
        )

        imap = asyncio.run(index_map(url))
        print(f"\n  mapa índice→campo construído pelo Introspector do repo: {len(imap)} índices")
        for name, (table, fields, kind) in sorted(imap.items()):
            print(f"    {name:14s} {table:9s} {kind:9s} {fields}")

        rows = []
        for label, sql_text, truth in CASES:
            with_idx = run_case(port, sql_text)
            used = sorted(with_idx.indexes)
            resolved: list[str] = []
            for name in used:
                if name in imap:
                    resolved.extend(imap[name][1])
            # what the plan itself exposes as text, if anything
            slots = {r: v for r, v in with_idx.slots.items() if v}
            in_text = truth is not None and any(
                truth in chunk for chunks in slots.values() for chunk in chunks
            )
            # how many leading fields of a composite the query really used:
            # `access` carries one value per field actually bound.
            access = (with_idx.slots.get("filter") or [""])[0]
            arity = access.count(",") + 1 if access.startswith("[") else None
            rows.append(
                {
                    "label": label,
                    "truth": truth,
                    "ops": sorted(with_idx.operators),
                    "indexes": used,
                    "resolved": resolved,
                    "in_text": in_text,
                    "arity": arity,
                    "slots": {r: c[:1] for r, c in slots.items()},
                    "ok": with_idx.ok,
                    "error": with_idx.error,
                }
            )
        report(rows, imap)
    finally:
        proc.terminate()
        proc.wait(timeout=10)
        print("\n(servidor de teste encerrado)")


def report(rows: list[dict], imap: dict) -> None:
    lines = ["# B2b — resolução índice → campo", ""]
    lines.append("O passo do matcher que o B2 deixou **inteiramente sem medição**: quando a")
    lines.append("query usa índice, o plano devolve só o NOME do índice. Dá para recuperar o")
    lines.append("campo? Fixture: `tests/fixtures/news_mini` + índices standard/composto/unique.")
    lines.append("")
    lines.append(
        f"Mapa construído pelo `Introspector` + `parse_index_ddl` do repo: "
        f"**{len(imap)} índices, zero código de parsing novo**."
    )
    lines.append("")
    lines.append(
        "| caso | operador | índice usado | campo resolvido | campo no texto do plano? | verdade |"
    )
    lines.append("|---|---|---|---|---|---|")
    for r in rows:
        ops = ", ".join(f"`{o}`" for o in r["ops"] if o not in {"SelectProject"}) or "—"
        idx = ", ".join(f"`{i}`" for i in r["indexes"]) or "—"
        res = ", ".join(f"`{f}`" for f in r["resolved"]) or "—"
        if r["arity"] and len(r["resolved"]) > r["arity"]:
            res += f" ⚠ só {r['arity']} usado(s)"
        text = "sim" if r["in_text"] else ("**não**" if r["indexes"] else "sim (scan)")
        lines.append(f"| {r['label']} | {ops} | {idx} | {res} | {text} | `{r['truth']}` |")
    lines.append("")

    indexed = [r for r in rows if r["indexes"]]
    hidden = [r for r in indexed if not r["in_text"]]
    recovered = [r for r in hidden if r["truth"] in r["resolved"]]
    lines.append(
        f"**{len(indexed)} casos usaram índice.** Em **{len(hidden)}** deles o campo "
        f"desapareceu do texto do plano; o mapa recuperou **{len(recovered)}**."
    )
    lines.append("")
    lost = [r for r in hidden if r["truth"] not in r["resolved"]]
    if lost:
        lines.append(
            "Não recuperados: "
            + ", ".join(
                f"{r['label']} (esperado `{r['truth']}`, resolveu {r['resolved'] or 'nada'})"
                for r in lost
            )
        )
        lines.append("")
    for r in rows:
        if r["slots"]:
            lines.append(f"- **{r['label']}** → {r['slots']}")
    text = "\n".join(lines) + "\n"
    out = HERE / "results" / "b2b_index_resolution.md"
    out.parent.mkdir(exist_ok=True)
    out.write_text(text)
    print("\n" + text)
    print(f"→ {out}")


if __name__ == "__main__":
    main()
