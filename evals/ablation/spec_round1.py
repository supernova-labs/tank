"""Round 1 spec: newsroom fixture, 6 variants, 8 tasks.

A spec module exposes:
  * ``TASKS``      — task list (see tasks.py for the shape)
  * ``variants()`` — dict variant name -> ontology JSON dict, or a plain string
                     for knowledge that is not an ontology (the ``none`` variant)
"""

import json

from ontology_full import build
from tasks import TASKS as TASKS  # noqa: PLC0414 — re-exported for gen_runs/score


def strip_keys(node, keys: set[str]):
    """Recursively remove ``keys`` wherever they appear."""
    if isinstance(node, dict):
        return {k: strip_keys(v, keys) for k, v in node.items() if k not in keys}
    if isinstance(node, list):
        return [strip_keys(item, keys) for item in node]
    return node


def minimal_of(full: dict) -> dict:
    return {
        "types": [
            {"name": t["name"], "table": t["table"], "text": t.get("text")} for t in full["types"]
        ]
    }


def none_of(full: dict) -> str:
    tables = [t["table"] for t in full["types"]] + [
        r["table"] for r in full["relations"] if r.get("table")
    ]
    return "Tables in the database: " + ", ".join(tables)


def variants() -> dict:
    full = json.loads(build().to_json())
    return {
        "full": full,
        "no_values": strip_keys(full, {"values"}),
        "no_locator": strip_keys(full, {"locator"}),
        "no_nature": strip_keys(full, {"nature"}),
        "minimal": minimal_of(full),
        "none": none_of(full),
    }
