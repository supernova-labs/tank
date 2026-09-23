# Declaration task

You are integrating Tank (an ontology-as-code retrieval library) into a project.
Write the project's ontology declaration exactly as specified, using the typed classes (Unit / Edge with Annotated markers).

## API reference (read these, nothing else from the library)

- `/Users/gyprado/dev/tank-spike/src/tank/typed.py`
- `/Users/gyprado/dev/tank-spike/tests/fixtures/news_mini/ontology_typed.py`

The first file is the API module; the second is a complete worked example from
another project.

## Specification

Project: a knowledge base. Declare THREE findable types, two relations, one scope and
one freshness rule:

- `author`, table `author`: queryable attribute `name` (string). No text field, no
  stable id.
- `kb_article`, table `kb_article`: nature original; searchable text in field `body`;
  stable identity from the field `slug`; queryable attributes `slug` (string),
  `status` (string, closed vocabulary: `draft`, `published`, `archived`) and
  `updated_at` (datetime). Vector search on field `emb`, 8 dimensions, cosine metric.
  Full-text search on field `body` with analyzer `az_kb`, language `english`.
- `summary`, table `summary`: nature derived; searchable text in field `text`;
  queryable attribute `created_at` (datetime).
- Relation `summarizes`: every summary points at its article through the record field
  `article` on the summary table (from `summary` to `kb_article`).
- Relation `written_by`: an edge from `kb_article` to `author` (edge table has the
  relation's name) carrying a ranking weight stored in the edge field `share`
  (higher is better).
- Scope `author`, reached via the relation `written_by`.
- Freshness: `kb_article` ages on the field `updated_at` with decay `45d`.

## Rules

- Declare everything as typed classes: subclass `Unit` / `Edge` from `tank`, use Annotated markers (Key, Text, Locate, Searchable, Ages, Weighted, Named, Embed, ...), Literal[...] for closed vocabularies, Link[...] for record fields, and derive the ontology with `Ontology.of(...)`. Do NOT build UnitType/Attr/Relation objects directly.
- Write your declaration to exactly this file (module-level variable `ontology`):
  `/Users/gyprado/dev/tank/evals/authoring/runs/round1/submissions/T3--typed--r2.py`
- Validate it by running (from Bash):
    cd /Users/gyprado/dev/tank-spike && uv run python /Users/gyprado/dev/tank/evals/authoring/judge.py --run-id T3--typed--r2 --arm typed --task 3 /Users/gyprado/dev/tank/evals/authoring/runs/round1/submissions/T3--typed--r2.py
  The judge tells you whether your declaration is exact and lists every divergence.
  You may submit at most 6 times — iterate until `"exact": true` or you run out.
- Do not read or modify anything under `evals/authoring/golds/`. Do not modify
  library code. Do not read the other API form's files.

## Deliverable

Return your structured output with: `run_id` = "T3--typed--r2", `final_exact` (did your
last judged submission report exact=true?), `submissions_used`, and `gave_up`.
