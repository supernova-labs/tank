"""`tank check` — the CLI that runs the validator and fails the build.

Usage:
    tank check --ontology ontology.py --url http://127.0.0.1:8019 --ns myns --db mydb

The ontology file is a plain Python module; by default the first module-level
``Ontology`` instance is used (name it ``ontology`` by convention, or pick one
with ``--ontology path.py:name``). A broken declaration raises on import — that
alone fails CI with the ONT-* codes, before any connection is made.

Exit codes: 0 = no failures; 1 = FAIL findings (or WARN/VACUOUS with --strict);
2 = usage/connection/declaration error.
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import os
import sys
from pathlib import Path

from tank.checks import run_check
from tank.ontology import Ontology, OntologyError


def load_ontology(spec: str) -> Ontology:
    path_str, _, attr = spec.partition(":")
    path = Path(path_str)
    if not path.exists():
        raise SystemExit(f"tank: ontology file not found: {path}")
    module_spec = importlib.util.spec_from_file_location("tank_user_ontology", path)
    assert module_spec and module_spec.loader
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)  # OntologyError propagates: broken build
    if attr:
        obj = getattr(module, attr, None)
        if not isinstance(obj, Ontology):
            raise SystemExit(f"tank: {path}:{attr} is not an Ontology instance")
        return obj
    candidates = [v for v in vars(module).values() if isinstance(v, Ontology)]
    if not candidates:
        raise SystemExit(f"tank: no Ontology instance found in {path}")
    if len(candidates) > 1:
        raise SystemExit(
            f"tank: multiple Ontology instances in {path}; pick one with --ontology {path}:name"
        )
    return candidates[0]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="tank")
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser("check", help="validate the database against the ontology")
    check.add_argument(
        "--ontology", default="ontology.py", help="path.py[:attr] (default: ontology.py)"
    )
    check.add_argument("--url", default=os.environ.get("SURREAL_URL", "http://127.0.0.1:8000"))
    check.add_argument("--ns", required=True, help="namespace to validate")
    check.add_argument("--db", required=True, help="database to validate")
    check.add_argument("--user", default=os.environ.get("SURREAL_USER", "root"))
    check.add_argument(
        "--pass", dest="password", default=os.environ.get("SURREAL_PASSWORD", "root")
    )
    check.add_argument("--json", action="store_true", help="machine-readable report")
    check.add_argument("--strict", action="store_true", help="WARN and VACUOUS also fail the build")
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    try:
        ontology = load_ontology(args.ontology)
    except OntologyError as err:
        print(f"tank: ontology is invalid\n{err}", file=sys.stderr)
        raise SystemExit(2) from err

    try:
        report = asyncio.run(
            run_check(
                ontology,
                url=args.url,
                namespace=args.ns,
                database=args.db,
                user=args.user,
                password=args.password,
            )
        )
    except Exception as err:  # connection/auth/unexpected — usage error, not a finding
        print(f"tank: check could not run: {err}", file=sys.stderr)
        raise SystemExit(2) from err

    print(report.model_dump_json(indent=2) if args.json else report.render_text())
    raise SystemExit(report.exit_code(strict=args.strict))


if __name__ == "__main__":
    main()
