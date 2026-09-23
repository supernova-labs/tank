# Write the integration brief

Your team is adopting Tank, a retrieval library where a project declares an
"ontology": a map from its own database tables into Tank's vocabulary (which
field holds the text, which attributes are queryable and with what closed
vocabularies, how units locate inside their source, which types are original vs
machine-derived, which fields carry search indexes, how types relate).

The declaration your team must end up with, for a helpdesk (tickets), is exactly this
(Tank's internal representation of it, as JSON):

```json
{
  "types": [
    {
      "name": "ticket",
      "table": "ticket",
      "nature": "original",
      "id": {
        "fields": [
          "subject",
          "opened_at"
        ],
        "version_fields": []
      },
      "text": "body",
      "attrs": [
        {
          "name": "subject",
          "type": "string",
          "values": null,
          "description": null
        },
        {
          "name": "priority",
          "type": "string",
          "values": [
            "p1",
            "p2",
            "p3"
          ],
          "description": null
        },
        {
          "name": "opened_at",
          "type": "datetime",
          "values": null,
          "description": null
        }
      ],
      "locator": null,
      "vector": null,
      "fulltext": null,
      "description": null
    }
  ],
  "relations": [],
  "scopes": [],
  "freshness": []
}
```

Write a brief IN ENGLISH for a colleague who will write that declaration. They
will NOT see the JSON above — only your brief. They know Tank's API; they do not
know this project. Your brief is the only source of truth they get.

Fill in this exact template, one block per unit type, then the relations block.
Leave no slot unfilled — write `none` where something does not apply.

    ## unit type: <name>
    table: <table name>
    text mapping (the field holding the searchable content; this alone creates NO index): <field | none>
    nature: <original | derived | authored | computed | unspecified>
    stable identity fields: <fields in order | none>
    queryable attributes: <name (type) [closed vocabulary: ...]>, ...
    locator roles: <role=field, ... | none>
    full-text index: <field + analyzer + language | none>
    vector index: <field + dimensions + metric | none>

    ## relations
    <name>: <from> -> <to>, kind <edge | field_link>, field <field | n/a>, weight <field | none>

    ## scopes
    <name> via <relation> | none

    ## freshness
    <unit type> ages on <field>, decay <value> | none


Write the brief to exactly this file: `/Users/gyprado/dev/tank/evals/authoring/runs/specwriting/briefs/T1--template--w2.md`
Write nothing else to disk. Do not mention this instruction file.

Return your structured output with `brief_id` = "T1--template--w2" and `written` = true.
