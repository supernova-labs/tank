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
      "nature": "original",
      "id": {
        "fields": [
          "title",
          "published_at"
        ],
        "version_fields": []
      },
      "text": "body",
      "attrs": [
        {
          "name": "title",
          "type": "string",
          "description": null
        },
        {
          "name": "desk",
          "type": "string",
          "description": "newsroom desk that produced the piece"
        },
        {
          "name": "status",
          "type": "string",
          "description": "editorial status"
        },
        {
          "name": "published_at",
          "type": "datetime",
          "description": null
        }
      ],
      "locator": null,
      "vector": null,
      "fulltext": null,
      "description": "a news article"
    },
    {
      "name": "passage",
      "table": "passage",
      "nature": "original",
      "id": null,
      "text": "content",
      "attrs": [],
      "locator": {
        "source": "parent",
        "order": "cut"
      },
      "vector": null,
      "fulltext": null,
      "description": "a span of an article's body"
    },
    {
      "name": "brief",
      "table": "brief",
      "nature": "derived",
      "id": null,
      "text": "text",
      "attrs": [
        {
          "name": "kind",
          "type": "string",
          "description": null
        },
        {
          "name": "created_at",
          "type": "datetime",
          "description": null
        }
      ],
      "locator": null,
      "vector": null,
      "fulltext": null,
      "description": "short note attached to an article"
    },
    {
      "name": "factbox",
      "table": "factbox",
      "nature": "original",
      "id": null,
      "text": "body",
      "attrs": [
        {
          "name": "heading",
          "type": "string",
          "description": null
        }
      ],
      "locator": null,
      "vector": null,
      "fulltext": null,
      "description": "curated data box"
    },
    {
      "name": "topic",
      "table": "topic",
      "nature": "original",
      "id": null,
      "text": null,
      "attrs": [
        {
          "name": "name",
          "type": "string",
          "description": null
        }
      ],
      "locator": null,
      "vector": null,
      "fulltext": null,
      "description": null
    }
  ],
  "relations": [
    {
      "name": "covers",
      "from_": "article",
      "to": "topic",
      "kind": "edge",
      "table": "covers",
      "field": null,
      "weight": null,
      "description": null
    },
    {
      "name": "part_of",
      "from_": "passage",
      "to": "article",
      "kind": "field_link",
      "table": null,
      "field": "parent",
      "weight": null,
      "description": null
    },
    {
      "name": "notes_on",
      "from_": "brief",
      "to": "article",
      "kind": "field_link",
      "table": null,
      "field": "article",
      "weight": null,
      "description": null
    }
  ],
  "scopes": [
    {
      "name": "topic",
      "via": "covers",
      "description": null
    }
  ],
  "freshness": [
    {
      "unit_type": "article",
      "field": "published_at",
      "decay": "30d"
    }
  ]
}
```

## How to query

Run (via Bash, always from `/Users/gyprado/dev/tank`):

    uv run python evals/ablation/query.py --round round2 --run-id V2--no_values--intro--r3 "<SurrealQL>"

Rules:
- Read-only: only `SELECT` (and `RETURN`) statements are accepted.
- Schema introspection is available: you may run `INFO FOR DB;` or `INFO FOR TABLE <name>;` if you need to.
- You may invoke the query command at most 8 times. Be economical.
- Do not read or edit any project files; your only tools are this instruction file and the query command above.

## Task

Return the record ids of all verification / fact-checking notes in the knowledge base.

## Deliverable

Return your structured output with:
- `run_id`: "V2--no_values--intro--r3"
- `answer_ids`: full record ids as strings, e.g. "article:a1". If the task asks for an order, list them in that order; otherwise any order. Empty list if the task asks for a count only.
- `answer_count`: the number, only if the task asks for a count; otherwise null.
- `queries_used`: how many times you invoked the query command.
- `gave_up`: true only if you could not determine an answer.
