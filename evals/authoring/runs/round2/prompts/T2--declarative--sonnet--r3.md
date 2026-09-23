# Declaration task

You are integrating Tank (an ontology-as-code retrieval library) into a project.
Write the project's ontology declaration exactly as specified, using the declarative objects (Ontology / UnitType / Attr / Relation / ...).

## API reference (read these, nothing else from the library)

- `/Users/gyprado/dev/tank-spike/src/tank/ontology.py`
- `/Users/gyprado/dev/tank-spike/tests/fixtures/news_mini/ontology.py`

The first file is the API module; the second is a complete worked example from
another project.

## Specification

Project: product documentation. Declare TWO findable types and their connection:

- `manual`, table `manual`: searchable text in field `body`; stable identity from the
  field `title`; queryable attribute `title` (string).
- `chunk`, table `chunk`: searchable text in field `content`; queryable attribute
  `pos` (int).
- Every chunk points at its manual through the record field `manual` on the chunk
  table. That connection is a relation named `chunk_of`, going from `chunk` to `manual`.
- The chunk's locator: the role `source` is played by the field `manual`; the role
  `order` is played by the field `pos`.

## Rules

- Declare everything with the declarative objects imported from `tank` (Ontology, UnitType, Attr, StableId, Locator, Vector, FullText, Relation, Weight, Scope, Freshness). Do NOT subclass Unit or Edge.
- Write your declaration to exactly this file (module-level variable `ontology`):
  `/Users/gyprado/dev/tank/evals/authoring/runs/round2/submissions/T2--declarative--sonnet--r3.py`
- Validate it by running (from Bash):
    cd /Users/gyprado/dev/tank-spike && uv run python /Users/gyprado/dev/tank/evals/authoring/judge.py --round round2 --run-id T2--declarative--sonnet--r3 --arm declarative --task 2 /Users/gyprado/dev/tank/evals/authoring/runs/round2/submissions/T2--declarative--sonnet--r3.py
  The judge tells you whether your declaration is exact and lists every divergence.
  You may submit at most 6 times — iterate until `"exact": true` or you run out.
- Do not read or modify anything under `evals/authoring/golds/`. Do not modify
  library code. Do not read the other API form's files.

## Deliverable

Return your structured output with: `run_id` = "T2--declarative--sonnet--r3", `final_exact` (did your
last judged submission report exact=true?), `submissions_used`, and `gave_up`.
