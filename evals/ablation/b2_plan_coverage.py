"""B2 — how much of a real agent query does the tier-3a plan actually explain?

The 0.2 gateway promises to answer "which attr was filtered, with what value, and
in what role" by reading SurrealDB's ``EXPLAIN`` instead of parsing SQL. That
promise has never been measured against queries anyone actually wrote.

This harness measures it offline, with no agent and no LLM: it replays every
SurrealQL statement the ablation agents produced (rounds 1 and 2, logged by
``query.py``), asks the server for the plan, runs the tier-3a matcher over it,
and reports what fraction of each observable the gateway would really have got.

    uv run python evals/ablation/b2_plan_coverage.py --port 8041

Needs a SurrealDB 3.x binary; the script seeds both fixtures into throwaway
in-memory databases and tears the server down when it finishes.
"""

from __future__ import annotations

import argparse
import base64
import collections
import importlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

# The 3.x binary. A machine-specific default is not a default: override with
# TANK_SURREAL_BINARY, or point at whatever `surreal` is on PATH.
BINARY = os.environ.get("TANK_SURREAL_BINARY") or shutil.which("surreal") or "surreal"
NS = "b2"

# Fields that are never a client attr: the record id and the implicit edge ends.
RESERVED = {"id", "in", "out"}

# Slots of the 3.x plan tree, and the role each one assigns to the names in it.
ROLE_OF_SLOT = {
    "predicate": "filter",
    "sort_keys": "sort",
    "projections": "projection",
    "group_by": "group",
    "fields": "computed",
    "access": "filter",
    "query": "fulltext",
    "expr": "projection",
}

ROUNDS = {
    "round1": ("ontology_full", "fixtures/newsroom.surql"),
    "round2": ("spec_round2", "fixtures/newsroom2.surql"),
}


# --------------------------------------------------------------------- server


def sql(port: int, db: str | None, body: str) -> list[dict]:
    auth = base64.b64encode(b"root:root").decode()
    headers = {"Authorization": f"Basic {auth}", "Accept": "application/json"}
    if db:
        headers["surreal-ns"] = NS
        headers["surreal-db"] = db
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/sql", data=body.encode(), headers=headers
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as exc:  # the error body IS the result
        return [{"status": "ERR", "result": exc.read().decode()[:400]}]
    except (urllib.error.URLError, OSError) as exc:
        return [{"status": "ERR", "result": f"transport: {exc}"}]


def boot(port: int) -> subprocess.Popen:
    proc = subprocess.Popen(
        [
            BINARY,
            "start",
            "--user",
            "root",
            "--pass",
            "root",
            "--bind",
            f"127.0.0.1:{port}",
            "--log",
            "error",
            "memory",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    for _ in range(80):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/version", timeout=1).read()
            return proc
        except (OSError, urllib.error.URLError):  # polling until it answers
            time.sleep(0.25)
    proc.kill()
    raise SystemExit(f"SurrealDB did not come up on {port}")


def seed(port: int) -> None:
    sql(port, None, f"DEFINE NAMESPACE {NS};")
    for round_name, (_, fixture) in ROUNDS.items():
        sql(port, None, f"USE NS {NS}; DEFINE DATABASE {round_name};")
        out = sql(port, round_name, (HERE / fixture).read_text())
        bad = [r for r in out if r.get("status") != "OK"]
        print(f"  {round_name}: {len(out)} statements, {len(bad)} failed")


# ---------------------------------------------------------------- vocabulary


def vocabulary(module_name: str) -> dict[str, set[str]]:
    """table -> declared field names the matcher is allowed to resolve against.

    declared_fields() alone is not enough: it never looks at Ontology.relations,
    so every field_link field would silently fail to resolve.
    """
    ontology = importlib.import_module(module_name).build()
    vocab: dict[str, set[str]] = {}
    for unit in ontology.types:
        vocab[unit.table] = set(unit.declared_fields()) - RESERVED
    for rel in ontology.relations:
        if rel.kind == "field_link" and rel.field:
            table = ontology.type_named(rel.from_).table
            vocab.setdefault(table, set()).add(rel.field)
        if rel.kind == "edge" and rel.table:
            vocab.setdefault(rel.table, set())
        if getattr(rel, "weight", None) and rel.weight and rel.table:
            vocab.setdefault(rel.table, set()).add(rel.weight.field)
    return vocab


# --------------------------------------------------------------- statements


def statements() -> dict[str, list[str]]:
    """Every SurrealQL string the agents actually sent, per round, in order."""
    out: dict[str, list[str]] = collections.defaultdict(list)
    for path in sorted(HERE.glob("runs/*/log/*.jsonl")):
        round_name = path.parts[-3]
        if round_name not in ROUNDS:
            continue
        for line in path.read_text().splitlines():
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if "sql" in entry and not entry.get("refused"):
                out[round_name].append(entry["sql"])
    return out


def kind_of(statement: str) -> str:
    """The gateway's tier-3a promise is about DATA queries. Introspection and
    anything else is counted, but never held against the plan's coverage."""
    head = statement.lstrip().split(None, 1)[0].upper() if statement.strip() else ""
    if head in {"SELECT", "RETURN"}:
        return "data"
    if head in {"INFO", "DESCRIBE", "SHOW"}:
        return "introspection"
    return "other"


def split_statements(text: str) -> list[str]:
    """Naive split on ';' outside string literals — enough to count how many
    calls carried more than one statement, which the 0.2 gateway refuses."""
    parts, buf, quote = [], [], None
    for ch in text:
        if quote:
            if ch == quote:
                quote = None
        elif ch in "'\"":
            quote = ch
        elif ch == ";":
            parts.append("".join(buf))
            buf = []
            continue
        buf.append(ch)
    parts.append("".join(buf))
    return [p.strip() for p in parts if p.strip()]


# ------------------------------------------------------------------- matcher

LITERAL = re.compile(r"'[^']*'|\"[^\"]*\"")
RECORD_ID = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*:[A-Za-z0-9_]+")

# SurrealQL keywords and operators. A token that is one of these is grammar,
# never a field — counting it as "referenced an undeclared name" would be the
# exact false positive the matcher exists to avoid.
BUILTIN_NS = {
    "math",
    "time",
    "string",
    "array",
    "duration",
    "type",
    "vector",
    "record",
    "object",
    "rand",
    "search",
    "crypto",
    "geo",
    "meta",
    "parse",
    "session",
    "http",
    "sleep",
    "encoding",
    "bytes",
    "not",
    "count",
}

KEYWORDS = {
    "select",
    "from",
    "where",
    "order",
    "by",
    "asc",
    "desc",
    "limit",
    "start",
    "group",
    "all",
    "and",
    "or",
    "not",
    "in",
    "inside",
    "outside",
    "contains",
    "containsall",
    "containsany",
    "containsnone",
    "containsnot",
    "intersects",
    "allinside",
    "anyinside",
    "noneinside",
    "is",
    "none",
    "null",
    "true",
    "false",
    "as",
    "value",
    "only",
    "split",
    "fetch",
    "with",
    "parallel",
    "timeout",
    "explain",
    "full",
    "let",
    "return",
    "if",
    "then",
    "else",
    "end",
    "type",
    "matches",
    "distinct",
    "omit",
    "index",
    "noindex",
    "count",
}
ELIDED = re.compile(r"\(\s*\.\.\.\s*\)")
IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*")


@dataclass
class Observation:
    ok: bool = False
    error: str = ""
    tables: set[str] = field(default_factory=set)
    slots: dict[str, list[str]] = field(default_factory=dict)
    elided: set[str] = field(default_factory=set)
    subquery: bool = False
    operators: set[str] = field(default_factory=set)
    indexes: set[str] = field(default_factory=set)
    resolved: set[tuple[str, str]] = field(default_factory=set)  # (attr, role)
    unresolved: set[tuple[str, str]] = field(default_factory=set)
    values_seen: int = 0


def walk(node: object, obs: Observation) -> None:
    if isinstance(node, list):
        for item in node:
            walk(item, obs)
        return
    if not isinstance(node, dict):
        return

    op = node.get("operator")
    if op:
        obs.operators.add(op)

    attrs = node.get("attributes") or {}
    for key in ("table", "tables"):
        value = attrs.get(key)
        if isinstance(value, str):
            obs.tables.add(value)
        elif isinstance(value, list):
            obs.tables.update(str(v) for v in value)
    if isinstance(attrs.get("index"), str):
        obs.indexes.add(attrs["index"])

    for slot, role in ROLE_OF_SLOT.items():
        value = attrs.get(slot)
        if not isinstance(value, str):
            continue
        obs.slots.setdefault(role, []).append(value)
        if ELIDED.search(value):
            obs.elided.add(role)

    for expr in node.get("expressions") or []:
        if isinstance(expr, dict) and expr.get("embedded_operators"):
            obs.subquery = True
            walk([e.get("plan") for e in expr["embedded_operators"]], obs)

    walk(node.get("children"), obs)


def match(obs: Observation, vocab: dict[str, set[str]]) -> None:
    """Steps 1-3 of the matcher: redact literals, tokenize, resolve, assign role."""
    allowed: set[str] = set()
    for table in obs.tables:
        allowed |= vocab.get(table, set())
    if not allowed:  # unknown table: resolve against everything declared
        for names in vocab.values():
            allowed |= names

    for role, raw_slots in obs.slots.items():
        for raw in raw_slots:
            obs.values_seen += len(LITERAL.findall(raw))
            # Literals out FIRST, replaced by whitespace — not by a placeholder.
            # The first version substituted "'<lit>'" and the tokenizer picked
            # `lit` straight back up, reporting an undeclared field 194 times.
            redacted = RECORD_ID.sub(" ", LITERAL.sub(" ", raw))
            for token in IDENT.findall(redacted):
                head = token.split(".")[0]
                if head in RESERVED or head.lower() in KEYWORDS:
                    continue
                if head.lower() in BUILTIN_NS:
                    continue
                if head in allowed:
                    obs.resolved.add((head, role))
                elif head not in obs.tables:
                    obs.unresolved.add((head, role))


def explain(port: int, db: str, statement: str, vocab: dict[str, set[str]]) -> Observation:
    obs = Observation()
    out = sql(port, db, f"{statement} EXPLAIN;")
    if not out or out[0].get("status") != "OK":
        obs.error = str(out[0].get("result", "?"))[:120] if out else "empty"
        return obs
    obs.ok = True
    walk(out[0].get("result"), obs)
    match(obs, vocab)
    return obs


# --------------------------------------------------------------------- report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8041)
    parser.add_argument("--limit", type=int, default=0, help="only N distinct statements per round")
    args = parser.parse_args()

    corpus = statements()
    print("Subindo SurrealDB e semeando as fixtures…")
    proc = boot(args.port)
    try:
        seed(args.port)
        rows = []
        for round_name, (module, _) in ROUNDS.items():
            vocab = vocabulary(module)
            raw = corpus[round_name]
            per_call = [split_statements(text) for text in raw]
            multi = sum(1 for parts in per_call if len(parts) > 1)
            flat = [p for parts in per_call for p in parts]
            distinct = sorted(set(flat))
            if args.limit:
                distinct = distinct[: args.limit]
            counts = collections.Counter(flat)

            print(
                f"\n{round_name}: {len(raw)} chamadas → {len(flat)} statements "
                f"({len(distinct)} distintos); {multi} chamadas com mais de um statement"
            )

            results = {}
            for i, stmt in enumerate(distinct, 1):
                if i % 50 == 0:
                    print(f"  … {i}/{len(distinct)}")
                results[stmt] = explain(args.port, round_name, stmt, vocab)
            rows.append((round_name, distinct, counts, results))
        report(rows)
    finally:
        proc.terminate()
        proc.wait(timeout=10)
        print("\n(servidor de teste encerrado)")


def _short_error(raw: str) -> str:
    """The server answers HTTP errors as a JSON blob; keep the human part."""
    try:
        return str(json.loads(raw).get("information", raw))[:70]
    except (json.JSONDecodeError, AttributeError, TypeError):  # not JSON, use as-is
        return raw[:70]


def report(rows: list) -> None:
    lines: list[str] = ["# B2 — cobertura real do plano (degrau 3a)", ""]
    lines.append("Medido sobre as statements que os agentes da ablação realmente escreveram.")
    lines.append("`ponderado` = por invocação real (tráfego); `distinto` = por forma de query.")
    lines.append("")

    for round_name, distinct, counts, results in rows:
        total_calls = sum(counts.values())
        lines.append(f"## {round_name}")
        lines.append("")

        data = [s for s in distinct if kind_of(s) == "data"]
        intro = [s for s in distinct if kind_of(s) == "introspection"]
        other = [s for s in distinct if kind_of(s) == "other"]
        data_calls = sum(counts[s] for s in data)
        lines.append(
            f"Statements distintos: **{len(data)} de dado** (SELECT/RETURN) · "
            f"{len(intro)} de introspecção · {len(other)} outros. "
            f"Tráfego de dado: {data_calls}/{total_calls} invocações "
            f"({100 * data_calls / max(total_calls, 1):.0f}%)."
        )
        lines.append("")
        lines.append(
            "Tudo abaixo é **sobre as statements de dado** — introspecção não tem plano "
            "por construção e não conta contra a cobertura."
        )
        lines.append("")

        def pct(pred, *, data=data, results=results, counts=counts, calls=data_calls):
            d = sum(1 for s in data if pred(results[s]))
            w = sum(counts[s] for s in data if pred(results[s]))
            return (
                f"{d}/{len(data)} ({100 * d / max(len(data), 1):.0f}%)",
                f"{w}/{calls} ({100 * w / max(calls, 1):.0f}%)",
            )

        checks = [
            ("EXPLAIN devolveu plano", lambda o: o.ok),
            ("tem slot de filtro (predicate)", lambda o: o.ok and "filter" in o.slots),
            ("tem slot de ordenação (sort_keys)", lambda o: o.ok and "sort" in o.slots),
            ("tem projeção", lambda o: o.ok and "projection" in o.slots),
            ("resolveu ao menos 1 attr declarado", lambda o: bool(o.resolved)),
            (
                "resolveu attr em papel de FILTRO",
                lambda o: any(r == "filter" for _, r in o.resolved),
            ),
            ("**elidiu algum slot** (arg de função)", lambda o: bool(o.elided)),
            ("**tem subquery**", lambda o: o.subquery),
            ("nome não resolvido no vocabulário", lambda o: bool(o.unresolved)),
            ("usou índice", lambda o: bool(o.indexes)),
        ]
        lines.append("| observável | distinto | ponderado por tráfego |")
        lines.append("|---|---|---|")
        for label, pred in checks:
            d, w = pct(pred)
            lines.append(f"| {label} | {d} | {w} |")
        lines.append("")

        def fully_observable(o: Observation) -> bool:
            return o.ok and not o.elided and not o.subquery and bool(o.resolved)

        d, w = pct(fully_observable)
        lines.append(
            f"**Plenamente observável** (plano ok, zero elisão, zero subquery, "
            f"ao menos um attr resolvido): **{d} distinto · {w} do tráfego**"
        )
        lines.append("")

        errs = collections.Counter(
            _short_error(results[s].error) for s in data if not results[s].ok
        )
        if errs:
            lines.append(
                "Motivos de plano ausente: "
                + ", ".join(f"`{k}` ×{v}" for k, v in errs.most_common(4))
            )
            lines.append("")

        ops = collections.Counter(op for s in data for op in results[s].operators)
        lines.append(
            "Operadores vistos: " + ", ".join(f"`{k}` ×{v}" for k, v in ops.most_common(8))
        )
        lines.append("")

        roles = collections.Counter(r for s in data for _, r in results[s].resolved)
        lines.append(
            "Attrs resolvidos por papel: "
            + (", ".join(f"{k} ×{v}" for k, v in roles.most_common()) or "nenhum")
        )
        unres = collections.Counter(n for s in data for n, _ in results[s].unresolved)
        if unres:
            lines.append("")
            lines.append(
                "Nomes não resolvidos (top 8): "
                + ", ".join(f"`{k}` ×{v}" for k, v in unres.most_common(8))
            )
        lines.append("")

    text = "\n".join(lines) + "\n"
    out = HERE / "results" / "b2_plan_coverage.md"
    out.parent.mkdir(exist_ok=True)
    out.write_text(text)
    print("\n" + text)
    print(f"→ {out}")


if __name__ == "__main__":
    main()
