# Declaration task

You are integrating Tank (an ontology-as-code retrieval library) into a project.
A colleague wrote the brief below; it is your only specification.

## The brief

Read it from: `/Users/gyprado/dev/tank/evals/authoring/runs/specwriting/briefs/T1--template--w1.md`

## API reference (read these, nothing else from the library)

- `/Users/gyprado/dev/tank-spike/src/tank/typed.py`
- `/Users/gyprado/dev/tank-spike/tests/fixtures/news_mini/ontology_typed.py`

The first file is the API module; the second is a complete worked example from
another project.

## Rules

- Declare everything as typed classes: subclass `Unit` / `Edge` from `tank`, use Annotated markers (Key, Text, Locate, Searchable, Ages, Weighted, Named, Embed, ...), Literal[...] for closed vocabularies, Link[...] for record fields, and derive the ontology with `Ontology.of(...)`. Do NOT build UnitType/Attr/Relation objects directly.
- Write your declaration to exactly this file (module-level variable `ontology`):
  `/Users/gyprado/dev/tank/evals/authoring/runs/specwriting_neutral/submissions/T1--template--w1--typed.py`
- Then run this command ONCE — it records your submission:
    cd /Users/gyprado/dev/tank-spike && uv run python /Users/gyprado/dev/tank/evals/authoring/judge.py --round specwriting_neutral --run-id T1--template--w1--typed --arm typed --task 1 /Users/gyprado/dev/tank/evals/authoring/runs/specwriting_neutral/submissions/T1--template--w1--typed.py
  You get ONE submission. Do not submit again, whatever it reports.
- Do not read or modify anything under `evals/authoring/golds/`.

## Deliverable

Return your structured output with `run_id` = "T1--template--w1--typed", `submitted` = true.
