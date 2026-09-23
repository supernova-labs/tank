# Declaration task

You are integrating Tank (an ontology-as-code retrieval library) into a project.
Write the project's ontology declaration exactly as specified, using the declarative objects (Ontology / UnitType / Attr / Relation / ...).

## API reference (read these, nothing else from the library)

- `/Users/gyprado/dev/tank-spike/src/tank/ontology.py`
- `/Users/gyprado/dev/tank-spike/tests/fixtures/news_mini/ontology.py`

The first file is the API module; the second is a complete worked example from
another project.

## Specification

The project's EXISTING declaration (your starting point — copy it into your
submission file and extend it): `/Users/gyprado/dev/tank/evals/authoring/starters/task4_declarative.py`

The project already declares its ontology — the starter file given above contains it.
Your submission must contain everything the starter declares, semantically unchanged,
PLUS:

- A new type `faq`, table `faq`: `text` mapping points at the field `answer` (text
  mapping only — no full-text index); stable identity from the field `question`;
  queryable attributes `question` (string) and `tag` (string, closed vocabulary:
  `howto`, `billing`, `bug`).
- A new relation `covers_manual`: an edge from `faq` to `manual` (edge table has the
  relation's name), no weight.

Declare full-text search or vector search ONLY where this specification explicitly says so — nowhere else.

## Rules

- Declare everything with the declarative objects imported from `tank` (Ontology, UnitType, Attr, StableId, Locator, Vector, FullText, Relation, Weight, Scope, Freshness). Do NOT subclass Unit or Edge.
- Write your declaration to exactly this file (module-level variable `ontology`):
  `/Users/gyprado/dev/tank/evals/authoring/runs/round3/submissions/T4--declarative--haiku--r3.py`
- Validate it by running (from Bash):
    cd /Users/gyprado/dev/tank-spike && uv run python /Users/gyprado/dev/tank/evals/authoring/judge.py --round round3 --run-id T4--declarative--haiku--r3 --arm declarative --task 4 /Users/gyprado/dev/tank/evals/authoring/runs/round3/submissions/T4--declarative--haiku--r3.py
  The judge tells you whether your declaration is exact and lists every divergence.
  You may submit at most 6 times — iterate until `"exact": true` or you run out.
- Do not read or modify anything under `evals/authoring/golds/`. Do not modify
  library code. Do not read the other API form's files.

## Deliverable

Return your structured output with: `run_id` = "T4--declarative--haiku--r3", `final_exact` (did your
last judged submission report exact=true?), `submissions_used`, and `gave_up`.
