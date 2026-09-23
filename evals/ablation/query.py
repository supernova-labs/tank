"""Read-only SurrealQL gateway for eval agents.

Every invocation is logged to ``runs/<round>/log/<run_id>.jsonl`` — the scorer
trusts this log (query count, introspection attempts, errors), never the
agent's self-report.

Usage:
    uv run python evals/ablation/query.py --run-id V1--full--intro--r1 "SELECT ..."
    uv run python evals/ablation/query.py --run-id ... --no-introspect "SELECT ..."
"""

import argparse
import base64
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

URL = os.environ.get("TANK_EVAL_URL", "http://127.0.0.1:8022")
NS = "tank_eval"
DB = "newsroom"
USER = os.environ.get("TANK_EVAL_USER", "root")
PASSWORD = os.environ.get("TANK_EVAL_PASS", "root")
DEFAULT_ROUND = os.environ.get("TANK_EVAL_ROUND", "round1")
MAX_OUTPUT_CHARS = 6000

READ_KEYWORDS = {"SELECT", "RETURN"}
INTROSPECT_KEYWORDS = {"INFO", "DESCRIBE", "SHOW"}


def first_keyword(statement: str) -> str:
    words = statement.strip().split()
    return words[0].upper() if words else ""


def check_statements(sql: str, allow_introspect: bool) -> str | None:
    """Return a refusal message, or None if the SQL is acceptable."""
    statements = [s for s in sql.split(";") if s.strip()]
    if not statements:
        return "empty query"
    for statement in statements:
        keyword = first_keyword(statement)
        if keyword in READ_KEYWORDS:
            continue
        if keyword in INTROSPECT_KEYWORDS:
            if allow_introspect:
                continue
            return (
                f"REFUSED: schema introspection ({keyword}) is not available in this "
                "session. Use SELECT only."
            )
        return f"REFUSED: only read statements (SELECT/RETURN) are allowed, got {keyword!r}."
    return None


def log(run_id: str, round_name: str, entry: dict) -> None:
    log_dir = Path(__file__).parent / "runs" / round_name / "log"
    log_dir.mkdir(parents=True, exist_ok=True)
    entry = {"ts": time.time(), "run_id": run_id, **entry}
    with (log_dir / f"{run_id}.jsonl").open("a") as f:
        f.write(json.dumps(entry) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--round", default=DEFAULT_ROUND)
    parser.add_argument("--no-introspect", action="store_true")
    parser.add_argument("sql")
    args = parser.parse_args()
    allow_introspect = not args.no_introspect

    refusal = check_statements(args.sql, allow_introspect)
    if refusal:
        log(
            args.run_id,
            args.round,
            {
                "sql": args.sql,
                "allow_introspect": allow_introspect,
                "refused": True,
                "ok": False,
            },
        )
        print(refusal)
        return 1

    auth = base64.b64encode(f"{USER}:{PASSWORD}".encode()).decode()
    request = urllib.request.Request(
        f"{URL}/sql",
        data=args.sql.encode(),
        headers={
            "Authorization": f"Basic {auth}",
            "Accept": "application/json",
            "surreal-ns": NS,
            "surreal-db": DB,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            results = json.load(response)
    except (urllib.error.URLError, OSError) as exc:
        log(
            args.run_id,
            args.round,
            {
                "sql": args.sql,
                "allow_introspect": allow_introspect,
                "refused": False,
                "ok": False,
                "error": str(exc),
            },
        )
        print(f"CONNECTION ERROR: {exc}")
        return 1

    ok = all(r.get("status") == "OK" for r in results)
    n_rows = sum(
        len(r["result"])
        for r in results
        if r.get("status") == "OK" and isinstance(r.get("result"), list)
    )
    log(
        args.run_id,
        args.round,
        {
            "sql": args.sql,
            "allow_introspect": allow_introspect,
            "refused": False,
            "ok": ok,
            "n_rows": n_rows,
        },
    )

    output = json.dumps(
        [{"status": r.get("status"), "result": r.get("result")} for r in results], indent=1
    )
    if len(output) > MAX_OUTPUT_CHARS:
        output = output[:MAX_OUTPUT_CHARS] + f"\n... [truncated at {MAX_OUTPUT_CHARS} chars]"
    print(output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
