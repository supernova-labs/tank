# Retrieval task

You are answering one question over a SurrealDB database (SurrealDB 2.x, namespace `tank_eval`, database `newsroom`). Work from the directory `/Users/gyprado/dev/tank`.

## What you know about the data

Tables in the database: article, passage, brief, topic, covers

## How to query

Run (via Bash, always from `/Users/gyprado/dev/tank`):

    uv run python evals/ablation/query.py --run-id L2--none--intro--r3 "<SurrealQL>"

Rules:
- Read-only: only `SELECT` (and `RETURN`) statements are accepted.
- Schema introspection is available: you may run `INFO FOR DB;` or `INFO FOR TABLE <name>;` if you need to.
- You may invoke the query command at most 8 times. Be economical.
- Do not read or edit any project files; your only tools are this instruction file and the query command above.

## Task

Return the record id of the opening passage (the one that appears first) of the article titled 'Climate accord signed'.

## Deliverable

Return your structured output with:
- `run_id`: "L2--none--intro--r3"
- `answer_ids`: full record ids as strings, e.g. "article:a1". If the task asks for an order, list them in that order; otherwise any order. Empty list if the task asks for a count only.
- `answer_count`: the number, only if the task asks for a count; otherwise null.
- `queries_used`: how many times you invoked the query command.
- `gave_up`: true only if you could not determine an answer.
