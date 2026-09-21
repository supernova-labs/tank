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

from pydantic import ValidationError

from tank.checks import run_check
from tank.ontology import Ontology, OntologyError


def _resolve_spec(spec: str) -> tuple[Path, str]:
    """Split ``path.py[:attr]`` without breaking Windows drive letters: the
    suffix is only treated as an attribute when the prefix exists as a file."""
    path = Path(spec)
    if path.exists():
        return path, ""
    head, sep, tail = spec.rpartition(":")
    if sep and Path(head).exists():
        return Path(head), tail
    print(f"tank: ontology file not found: {spec}", file=sys.stderr)
    raise SystemExit(2)


def load_ontology(spec: str) -> Ontology:
    path, attr = _resolve_spec(spec)
    module_spec = importlib.util.spec_from_file_location("tank_user_ontology", path)
    assert module_spec and module_spec.loader
    module = importlib.util.module_from_spec(module_spec)
    # the user's module may import siblings — make its directory importable
    sys.path.insert(0, str(path.parent.resolve()))
    try:
        module_spec.loader.exec_module(module)  # OntologyError propagates: broken build
    finally:
        sys.path.remove(str(path.parent.resolve()))
    if attr:
        obj = getattr(module, attr, None)
        if not isinstance(obj, Ontology):
            print(f"tank: {path}:{attr} is not an Ontology instance", file=sys.stderr)
            raise SystemExit(2)
        return obj
    candidates = [v for v in vars(module).values() if isinstance(v, Ontology)]
    if not candidates:
        print(f"tank: no Ontology instance found in {path}", file=sys.stderr)
        raise SystemExit(2)
    if len(candidates) > 1:
        print(
            f"tank: multiple Ontology instances in {path}; pick one with --ontology {path}:name",
            file=sys.stderr,
        )
        raise SystemExit(2)
    return candidates[0]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="tank")
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser("check", help="validate the database against the ontology")
    check.add_argument(
        "--ontology", default="ontology.py", help="path.py[:attr] (default: ontology.py)"
    )
    check.add_argument("--url", default=os.environ.get("SURREAL_URL", "http://127.0.0.1:8000"))
    check.add_argument(
        "--ns", default=os.environ.get("SURREAL_NS"), help="namespace to validate (env SURREAL_NS)"
    )
    check.add_argument(
        "--db", default=os.environ.get("SURREAL_DB"), help="database to validate (env SURREAL_DB)"
    )
    check.add_argument("--user", default=os.environ.get("SURREAL_USER", "root"))
    check.add_argument(
        "--pass", dest="password", default=os.environ.get("SURREAL_PASSWORD", "root")
    )
    check.add_argument("--json", action="store_true", help="machine-readable report")
    check.add_argument("--strict", action="store_true", help="WARN and VACUOUS also fail the build")
    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.ns or not args.db:
        parser.error("--ns and --db are required (flags or SURREAL_NS/SURREAL_DB env vars)")
    try:
        ontology = load_ontology(args.ontology)
    except OntologyError as err:
        print(f"tank: ontology is invalid\n{err}", file=sys.stderr)
        raise SystemExit(2) from err
    except SystemExit:
        raise
    except (ValidationError, Exception) as err:  # any failure loading the
        # user's module (pydantic shape errors, ImportError, SyntaxError) is a
        # declaration/usage problem: exit 2, never confused with check findings (1)
        print(f"tank: could not load ontology: {err}", file=sys.stderr)
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
