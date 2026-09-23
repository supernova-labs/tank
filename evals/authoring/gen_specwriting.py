"""Round 4 — how often does an AI-written spec induce a wrong declaration?

Two stages per brief:
  1. a WRITER agent sees the gold IR (the truth of what must be declared) and
     writes a natural-language brief for a colleague — in free prose, or into a
     structured template that forces explicit index/text declarations (the
     mitigation under test);
  2. IMPLEMENTER agents see ONLY that brief and declare the ontology, one
     submission each, no judge-feedback loop — so the score measures how much
     truth the brief carried, not how well the loop repairs it.

Reuses the authoring judge and golds. Usage:
    uv run python evals/authoring/gen_specwriting.py [--round specwriting] [--writers 3]
"""

import argparse
import importlib.util
import json
import os
from pathlib import Path

HERE = Path(__file__).parent
# The checkout the typed arm is judged against (the spike branch).
WORKTREE = os.environ.get("TANK_SPIKE_WORKTREE", "../tank-spike")
TASKS = [1, 2, 3]
STYLES = ["free", "template"]

DOMAIN = {
    1: "a helpdesk (tickets)",
    2: "product documentation (manuals split into chunks)",
    3: "a knowledge base (articles, authors, machine-written summaries)",
}

ARM_RULE = {
    "declarative": (
        "Declare everything with the declarative objects imported from `tank` "
        "(Ontology, UnitType, Attr, StableId, Locator, Vector, FullText, Relation, "
        "Weight, Scope, Freshness). Do NOT subclass Unit or Edge."
    ),
    "typed": (
        "Declare everything as typed classes: subclass `Unit` / `Edge` from `tank`, "
        "use Annotated markers (Key, Text, Locate, Searchable, Ages, Weighted, Named, "
        "Embed, ...), Literal[...] for closed vocabularies, Link[...] for record "
        "fields, and derive the ontology with `Ontology.of(...)`. Do NOT build "
        "UnitType/Attr/Relation objects directly."
    ),
}
ARM_DOCS = {
    "declarative": [
        f"{WORKTREE}/src/tank/ontology.py",
        f"{WORKTREE}/tests/fixtures/news_mini/ontology.py",
    ],
    "typed": [
        f"{WORKTREE}/src/tank/typed.py",
        f"{WORKTREE}/tests/fixtures/news_mini/ontology_typed.py",
    ],
}

TEMPLATE_FORM = """\
Fill in this exact template, one block per unit type, then the relations block.
Leave no slot unfilled — write `none` where something does not apply.

    ## unit type: <name>
    table: <table name>
    text mapping (the field holding the searchable content; this alone creates NO index): <field | none>
    nature: <original | derived | authored | computed | unspecified>
    stable identity fields: <fields in order | none>
    queryable attributes: <name (type) [closed vocabulary: ...]>, ...
    locator roles: <role=field, ... | none>
    full-text index: <field + analyzer + language | none>
    vector index: <field + dimensions + metric | none>

    ## relations
    <name>: <from> -> <to>, kind <edge | field_link>, field <field | n/a>, weight <field | none>

    ## scopes
    <name> via <relation> | none

    ## freshness
    <unit type> ages on <field>, decay <value> | none
"""

WRITER_PROMPT = """\
# Write the integration brief

Your team is adopting Tank, a retrieval library where a project declares an
"ontology": a map from its own database tables into Tank's vocabulary (which
field holds the text, which attributes are queryable and with what closed
vocabularies, how units locate inside their source, which types are original vs
machine-derived, which fields carry search indexes, how types relate).

The declaration your team must end up with, for {domain}, is exactly this
(Tank's internal representation of it, as JSON):

```json
{gold}
```

Write a brief IN ENGLISH for a colleague who will write that declaration. They
will NOT see the JSON above — only your brief. They know Tank's API; they do not
know this project. Your brief is the only source of truth they get.

{style_instruction}

Write the brief to exactly this file: `{brief_path}`
Write nothing else to disk. Do not mention this instruction file.

Return your structured output with `brief_id` = "{brief_id}" and `written` = true.
"""

STYLE_INSTRUCTION = {
    "free": (
        "Write it as you normally would: clear prose, your own words, whatever "
        "structure you think communicates best."
    ),
    "template": TEMPLATE_FORM,
}

IMPLEMENTER_PROMPT = """\
# Declaration task

You are integrating Tank (an ontology-as-code retrieval library) into a project.
A colleague wrote the brief below; it is your only specification.

## The brief

Read it from: `{brief_path}`

## API reference (read these, nothing else from the library)

{docs_list}

The first file is the API module; the second is a complete worked example from
another project.

## Rules

- {arm_rule}
{fidelity_rule}- Write your declaration to exactly this file (module-level variable `ontology`):
  `{submission_path}`
- Then run this command ONCE — it records your submission:
    cd {worktree} && uv run python {judge} --round {round} --run-id {run_id} --arm {arm} --task {task} {submission_path}
  You get ONE submission. Do not submit again, whatever it reports.
- Do not read or modify anything under `evals/authoring/golds/`.

## Deliverable

Return your structured output with `run_id` = "{run_id}", `submitted` = true.
"""


def gold_json(task: int) -> str:
    path = HERE / "golds" / f"task{task}.py"
    spec = importlib.util.spec_from_file_location(f"gold{task}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return json.dumps(module.build().model_dump(), indent=2, default=str)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--round", default="specwriting")
    parser.add_argument("--writers", type=int, default=3)
    parser.add_argument(
        "--neutral",
        action="store_true",
        help=(
            "drop the anti-over-declaration rule from the implementer prompt "
            "(round 4 shipped with it; the neutral variant decomposes that confound)"
        ),
    )
    parser.add_argument(
        "--briefs-from",
        default=None,
        help="reuse briefs already written for another round (keeps the writers constant)",
    )
    args = parser.parse_args()
    fidelity_rule = (
        ""
        if args.neutral
        else (
            "- Follow the brief exactly. Where the brief is silent about something, "
            "declare\n  only what the brief actually asks for.\n"
        )
    )

    round_dir = HERE / "runs" / args.round
    for sub in ("writer_prompts", "impl_prompts", "briefs", "submissions"):
        (round_dir / sub).mkdir(parents=True, exist_ok=True)

    manifest = []
    for task in TASKS:
        gold = gold_json(task)
        for style in STYLES:
            for writer in range(1, args.writers + 1):
                brief_id = f"T{task}--{style}--w{writer}"
                brief_source = (
                    HERE / "runs" / args.briefs_from if args.briefs_from else round_dir
                )
                brief_path = brief_source / "briefs" / f"{brief_id}.md"
                (round_dir / "writer_prompts" / f"{brief_id}.md").write_text(
                    WRITER_PROMPT.format(
                        domain=DOMAIN[task],
                        gold=gold,
                        style_instruction=STYLE_INSTRUCTION[style],
                        brief_path=brief_path,
                        brief_id=brief_id,
                    )
                )
                arms = []
                for arm in ("declarative", "typed"):
                    run_id = f"{brief_id}--{arm}"
                    submission_path = round_dir / "submissions" / f"{run_id}.py"
                    (round_dir / "impl_prompts" / f"{run_id}.md").write_text(
                        IMPLEMENTER_PROMPT.format(
                            brief_path=brief_path,
                            docs_list="\n".join(f"- `{d}`" for d in ARM_DOCS[arm]),
                            arm_rule=ARM_RULE[arm],
                            fidelity_rule=fidelity_rule,
                            submission_path=submission_path,
                            worktree=WORKTREE,
                            judge=HERE / "judge.py",
                            round=args.round,
                            run_id=run_id,
                            arm=arm,
                            task=task,
                        )
                    )
                    arms.append({"run_id": run_id, "arm": arm})
                manifest.append(
                    {
                        "brief_id": brief_id,
                        "task": task,
                        "style": style,
                        "writer": writer,
                        "arms": arms,
                    }
                )

    (round_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(f"{len(manifest)} briefs → {2 * len(manifest)} implementations → {round_dir}")


if __name__ == "__main__":
    main()
