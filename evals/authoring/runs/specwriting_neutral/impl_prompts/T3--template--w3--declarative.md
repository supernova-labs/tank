# Declaration task

You are integrating Tank (an ontology-as-code retrieval library) into a project.
A colleague wrote the brief below; it is your only specification.

## The brief

Read it from: `/Users/gyprado/dev/tank/evals/authoring/runs/specwriting/briefs/T3--template--w3.md`

## API reference (read these, nothing else from the library)

- `/Users/gyprado/dev/tank-spike/src/tank/ontology.py`
- `/Users/gyprado/dev/tank-spike/tests/fixtures/news_mini/ontology.py`

The first file is the API module; the second is a complete worked example from
another project.

## Rules

- Declare everything with the declarative objects imported from `tank` (Ontology, UnitType, Attr, StableId, Locator, Vector, FullText, Relation, Weight, Scope, Freshness). Do NOT subclass Unit or Edge.
- Write your declaration to exactly this file (module-level variable `ontology`):
  `/Users/gyprado/dev/tank/evals/authoring/runs/specwriting_neutral/submissions/T3--template--w3--declarative.py`
- Then run this command ONCE — it records your submission:
    cd /Users/gyprado/dev/tank-spike && uv run python /Users/gyprado/dev/tank/evals/authoring/judge.py --round specwriting_neutral --run-id T3--template--w3--declarative --arm declarative --task 3 /Users/gyprado/dev/tank/evals/authoring/runs/specwriting_neutral/submissions/T3--template--w3--declarative.py
  You get ONE submission. Do not submit again, whatever it reports.
- Do not read or modify anything under `evals/authoring/golds/`.

## Deliverable

Return your structured output with `run_id` = "T3--template--w3--declarative", `submitted` = true.
