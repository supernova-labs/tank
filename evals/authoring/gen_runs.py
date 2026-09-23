"""Generate the authoring-eval run matrix: one prompt file per
(task x arm x repetition), plus a manifest.

Usage: uv run python evals/authoring/gen_runs.py [--round round1] [--reps 5]
"""

import argparse
import os
import importlib
import json
from pathlib import Path

HERE = Path(__file__).parent
# The checkout the typed arm is judged against (the spike branch).
WORKTREE = os.environ.get("TANK_SPIKE_WORKTREE", "../tank-spike")

ARMS = {
    "declarative": {
        "label": "the declarative objects (Ontology / UnitType / Attr / Relation / ...)",
        "docs": [
            f"{WORKTREE}/src/tank/ontology.py",
            f"{WORKTREE}/tests/fixtures/news_mini/ontology.py",
        ],
        "rule": (
            "Declare everything with the declarative objects imported from `tank` "
            "(Ontology, UnitType, Attr, StableId, Locator, Vector, FullText, Relation, "
            "Weight, Scope, Freshness). Do NOT subclass Unit or Edge."
        ),
    },
    "typed": {
        "label": "the typed classes (Unit / Edge with Annotated markers)",
        "docs": [
            f"{WORKTREE}/src/tank/typed.py",
            f"{WORKTREE}/tests/fixtures/news_mini/ontology_typed.py",
        ],
        "rule": (
            "Declare everything as typed classes: subclass `Unit` / `Edge` from `tank`, "
            "use Annotated markers (Key, Text, Locate, Searchable, Ages, Weighted, Named, "
            "Embed, ...), Literal[...] for closed vocabularies, Link[...] for record "
            "fields, and derive the ontology with `Ontology.of(...)`. Do NOT build "
            "UnitType/Attr/Relation objects directly."
        ),
    },
}

PROMPT_TEMPLATE = """\
# Declaration task

You are integrating Tank (an ontology-as-code retrieval library) into a project.
Write the project's ontology declaration exactly as specified, using {arm_label}.

## API reference (read these, nothing else from the library)

{docs_list}

The first file is the API module; the second is a complete worked example from
another project.

## Specification

{starter_block}{brief}

## Rules

- {arm_rule}
- Write your declaration to exactly this file (module-level variable `ontology`):
  `{submission_path}`
- Validate it by running (from Bash):
    cd {worktree} && uv run python {judge} --round {round} --run-id {run_id} --arm {arm} --task {task} {submission_path}
  The judge tells you whether your declaration is exact and lists every divergence.
  You may submit at most 6 times — iterate until `"exact": true` or you run out.
- Do not read or modify anything under `evals/authoring/golds/`. Do not modify
  library code. Do not read the other API form's files.

## Deliverable

Return your structured output with: `run_id` = "{run_id}", `final_exact` (did your
last judged submission report exact=true?), `submissions_used`, and `gave_up`.
"""

STARTER_BLOCK = """\
The project's EXISTING declaration (your starting point — copy it into your
submission file and extend it): `{starter}`

"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--round", default="round1")
    parser.add_argument("--reps", type=int, default=5)
    parser.add_argument(
        "--models",
        default="sonnet",
        help="comma-separated model labels; each becomes a run dimension (e.g. sonnet,haiku)",
    )
    parser.add_argument("--specs", default="specs", help="specs module (specs | specs_v2)")
    args = parser.parse_args()
    models = [m.strip() for m in args.models.split(",") if m.strip()]
    tasks = importlib.import_module(args.specs).TASKS

    round_dir = HERE / "runs" / args.round
    prompts_dir = round_dir / "prompts"
    submissions_dir = round_dir / "submissions"
    prompts_dir.mkdir(parents=True, exist_ok=True)
    submissions_dir.mkdir(parents=True, exist_ok=True)

    manifest = []
    for task_id, task in tasks.items():
        for arm, arm_spec in ARMS.items():
            for model in models:
                run_ids = [
                    f"T{task_id}--{arm}--r{rep}"
                    if models == ["sonnet"]
                    else f"T{task_id}--{arm}--{model}--r{rep}"
                    for rep in range(1, args.reps + 1)
                ]
                for rep, run_id in enumerate(run_ids, start=1):
                    submission_path = submissions_dir / f"{run_id}.py"
                    starter_block = ""
                    if task_id == 4:
                        starter = HERE / "starters" / f"task4_{arm}.py"
                        starter_block = STARTER_BLOCK.format(starter=starter)
                    prompt = PROMPT_TEMPLATE.format(
                        arm_label=arm_spec["label"],
                        docs_list="\n".join(f"- `{d}`" for d in arm_spec["docs"]),
                        starter_block=starter_block,
                        brief=task["brief"],
                        arm_rule=arm_spec["rule"],
                        submission_path=submission_path,
                        worktree=WORKTREE,
                        judge=HERE / "judge.py",
                        round=args.round,
                        run_id=run_id,
                        arm=arm,
                        task=task_id,
                    )
                    (prompts_dir / f"{run_id}.md").write_text(prompt)
                    manifest.append(
                        {
                            "run_id": run_id,
                            "task": task_id,
                            "arm": arm,
                            "model": model,
                            "rep": rep,
                            "prompt_path": str(prompts_dir / f"{run_id}.md"),
                        }
                    )

    (round_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(f"{len(manifest)} runs → {round_dir}")


if __name__ == "__main__":
    main()
