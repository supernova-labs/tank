# Declaration task

You are integrating Tank (an ontology-as-code retrieval library) into a project.
Write the project's ontology declaration exactly as specified, using the typed classes (Unit / Edge with Annotated markers).

## API reference (read these, nothing else from the library)

- `/Users/gyprado/dev/tank-spike/src/tank/typed.py`
- `/Users/gyprado/dev/tank-spike/tests/fixtures/news_mini/ontology_typed.py`

The first file is the API module; the second is a complete worked example from
another project.

## Specification

Project: a helpdesk. Declare ONE findable type:

- `ticket`, stored in table `ticket`.
- Its searchable text lives in the field `body`.
- Epistemic nature: original.
- Stable identity is derived from the fields `subject` and `opened_at` (in this order).
- Queryable attributes: `subject` (string), `priority` (string, closed vocabulary:
  `p1`, `p2`, `p3`), `opened_at` (datetime).

## Rules

- Declare everything as typed classes: subclass `Unit` / `Edge` from `tank`, use Annotated markers (Key, Text, Locate, Searchable, Ages, Weighted, Named, Embed, ...), Literal[...] for closed vocabularies, Link[...] for record fields, and derive the ontology with `Ontology.of(...)`. Do NOT build UnitType/Attr/Relation objects directly.
- Write your declaration to exactly this file (module-level variable `ontology`):
  `/Users/gyprado/dev/tank/evals/authoring/runs/round2/submissions/T1--typed--sonnet--r5.py`
- Validate it by running (from Bash):
    cd /Users/gyprado/dev/tank-spike && uv run python /Users/gyprado/dev/tank/evals/authoring/judge.py --round round2 --run-id T1--typed--sonnet--r5 --arm typed --task 1 /Users/gyprado/dev/tank/evals/authoring/runs/round2/submissions/T1--typed--sonnet--r5.py
  The judge tells you whether your declaration is exact and lists every divergence.
  You may submit at most 6 times — iterate until `"exact": true` or you run out.
- Do not read or modify anything under `evals/authoring/golds/`. Do not modify
  library code. Do not read the other API form's files.

## Deliverable

Return your structured output with: `run_id` = "T1--typed--sonnet--r5", `final_exact` (did your
last judged submission report exact=true?), `submissions_used`, and `gave_up`.
