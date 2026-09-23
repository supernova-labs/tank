# Declaration task

You are integrating Tank (an ontology-as-code retrieval library) into a project.
Write the project's ontology declaration exactly as specified, using the declarative objects (Ontology / UnitType / Attr / Relation / ...).

## API reference (read these, nothing else from the library)

- `/Users/gyprado/dev/tank-spike/src/tank/ontology.py`
- `/Users/gyprado/dev/tank-spike/tests/fixtures/news_mini/ontology.py`

The first file is the API module; the second is a complete worked example from
another project.

## Specification

Project: a helpdesk. Declare ONE findable type:

- `ticket`, stored in table `ticket`.
- The type's `text` mapping points at the field `body` (this is only the text
  mapping — it does NOT imply any full-text index).
- Epistemic nature: original.
- Stable identity is derived from the fields `subject` and `opened_at` (in this order).
- Queryable attributes: `subject` (string), `priority` (string, closed vocabulary:
  `p1`, `p2`, `p3`), `opened_at` (datetime).

Declare full-text search or vector search ONLY where this specification explicitly says so — nowhere else.

## Rules

- Declare everything with the declarative objects imported from `tank` (Ontology, UnitType, Attr, StableId, Locator, Vector, FullText, Relation, Weight, Scope, Freshness). Do NOT subclass Unit or Edge.
- Write your declaration to exactly this file (module-level variable `ontology`):
  `/Users/gyprado/dev/tank/evals/authoring/runs/round3/submissions/T1--declarative--haiku--r3.py`
- Validate it by running (from Bash):
    cd /Users/gyprado/dev/tank-spike && uv run python /Users/gyprado/dev/tank/evals/authoring/judge.py --round round3 --run-id T1--declarative--haiku--r3 --arm declarative --task 1 /Users/gyprado/dev/tank/evals/authoring/runs/round3/submissions/T1--declarative--haiku--r3.py
  The judge tells you whether your declaration is exact and lists every divergence.
  You may submit at most 6 times — iterate until `"exact": true` or you run out.
- Do not read or modify anything under `evals/authoring/golds/`. Do not modify
  library code. Do not read the other API form's files.

## Deliverable

Return your structured output with: `run_id` = "T1--declarative--haiku--r3", `final_exact` (did your
last judged submission report exact=true?), `submissions_used`, and `gave_up`.
