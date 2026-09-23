"""Generate the run matrix for one ablation round: variant JSONs, per-run prompt
files, and a manifest for the orchestrator.

Variants are produced by *deleting keys* from the full ontology's JSON export —
removing information, never falsifying it (constructing a weaker ``Ontology``
would fill ablated fields with defaults, e.g. ``nature="original"`` on a
derived type). Each round has a spec module (``spec_round1``, ``spec_round2``)
exposing ``TASKS`` and ``variants()``.

Usage: uv run python evals/ablation/gen_runs.py [--round round1] [--spec spec_round1] [--reps 3]
"""

import argparse
import importlib
import json
from pathlib import Path

HERE = Path(__file__).parent

CONDITIONS = ["intro", "nointro"]

CONDITION_TEXT = {
    "intro": (
        "Schema introspection is available: you may run `INFO FOR DB;` or "
        "`INFO FOR TABLE <name>;` if you need to."
    ),
    "nointro": (
        "Schema introspection (`INFO`, `DESCRIBE`) is NOT available — such queries "
        "will be refused and still count against your query budget. Use `SELECT` only."
    ),
}


PROMPT_TEMPLATE = """\
# Retrieval task

You are answering one question over a SurrealDB database (SurrealDB 2.x, namespace \
`tank_eval`, database `newsroom`). Work from the directory the repository root.

## What you know about the data

{knowledge}

## How to query

Run (via Bash, always from the repository root):

    uv run python evals/ablation/query.py --round {round} --run-id {run_id}{introspect_flag} "<SurrealQL>"

Rules:
- Read-only: only `SELECT` (and `RETURN`) statements are accepted.
- {condition_text}
- You may invoke the query command at most 8 times. Be economical.
- Do not read or edit any project files; your only tools are this instruction file and \
the query command above.

## Task

{task}

## Deliverable

Return your structured output with:
- `run_id`: "{run_id}"
- `answer_ids`: full record ids as strings, e.g. "article:a1". If the task asks for an \
order, list them in that order; otherwise any order. Empty list if the task asks for a \
count only.
- `answer_count`: the number, only if the task asks for a count; otherwise null.
- `queries_used`: how many times you invoked the query command.
- `gave_up`: true only if you could not determine an answer.
"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--round", default="round1")
    parser.add_argument("--spec", default="spec_round1")
    parser.add_argument("--reps", type=int, default=3)
    args = parser.parse_args()

    spec = importlib.import_module(args.spec)
    round_dir = HERE / "runs" / args.round
    prompts_dir = round_dir / "prompts"
    variants_dir = round_dir / "variants"
    prompts_dir.mkdir(parents=True, exist_ok=True)
    variants_dir.mkdir(parents=True, exist_ok=True)

    variants = spec.variants()
    for name, declared in variants.items():
        path = variants_dir / f"{name}.json"
        path.write_text(json.dumps(declared, indent=2) if isinstance(declared, dict) else declared)

    manifest = []
    for variant, declared in variants.items():
        if isinstance(declared, dict):
            knowledge = (
                "The project declares this ontology over its tables (JSON):\n\n```json\n"
                + json.dumps(declared, indent=2)
                + "\n```"
            )
        else:
            knowledge = declared
        for condition in CONDITIONS:
            introspect_flag = "" if condition == "intro" else " --no-introspect"
            for task in spec.TASKS:
                for rep in range(1, args.reps + 1):
                    run_id = f"{task['id']}--{variant}--{condition}--r{rep}"
                    prompt = PROMPT_TEMPLATE.format(
                        knowledge=knowledge,
                        run_id=run_id,
                        round=args.round,
                        introspect_flag=introspect_flag,
                        condition_text=CONDITION_TEXT[condition],
                        task=task["prompt"],
                    )
                    path = prompts_dir / f"{run_id}.md"
                    path.write_text(prompt)
                    manifest.append(
                        {
                            "run_id": run_id,
                            "task": task["id"],
                            "category": task["category"],
                            "variant": variant,
                            "condition": condition,
                            "rep": rep,
                            "prompt_path": str(path),
                        }
                    )

    (round_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(f"{len(manifest)} runs → {round_dir}")


if __name__ == "__main__":
    main()
