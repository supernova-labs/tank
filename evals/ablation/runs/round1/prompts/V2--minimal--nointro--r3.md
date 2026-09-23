# Retrieval task

You are answering one question over a SurrealDB database (SurrealDB 2.x, namespace `tank_eval`, database `newsroom`). Work from the directory `/Users/gyprado/dev/tank`.

## What you know about the data

The project declares this ontology over its tables (JSON):

```json
{
  "types": [
    {
      "name": "article",
      "table": "article",
      "text": "body"
    },
    {
      "name": "passage",
      "table": "passage",
      "text": "content"
    },
    {
      "name": "brief",
      "table": "brief",
      "text": "text"
    },
    {
      "name": "topic",
      "table": "topic",
      "text": null
    }
  ]
}
```

## How to query

Run (via Bash, always from `/Users/gyprado/dev/tank`):

    uv run python evals/ablation/query.py --run-id V2--minimal--nointro--r3 --no-introspect "<SurrealQL>"

Rules:
- Read-only: only `SELECT` (and `RETURN`) statements are accepted.
- Schema introspection (`INFO`, `DESCRIBE`) is NOT available — such queries will be refused and still count against your query budget. Use `SELECT` only.
- You may invoke the query command at most 8 times. Be economical.
- Do not read or edit any project files; your only tools are this instruction file and the query command above.

## Task

Return the record ids of all verification / fact-checking notes in the knowledge base.

## Deliverable

Return your structured output with:
- `run_id`: "V2--minimal--nointro--r3"
- `answer_ids`: full record ids as strings, e.g. "article:a1". If the task asks for an order, list them in that order; otherwise any order. Empty list if the task asks for a count only.
- `answer_count`: the number, only if the task asks for a count; otherwise null.
- `queries_used`: how many times you invoked the query command.
- `gave_up`: true only if you could not determine an answer.
