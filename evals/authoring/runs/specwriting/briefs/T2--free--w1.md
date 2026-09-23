# Integration brief: product documentation (manuals + chunks)

We're onboarding a documentation corpus into Tank. The source data lives in two tables: `manual` and `chunk`. Manuals get split into chunks (this splitting already happened upstream — we're just declaring the existing tables, not performing the chunking). Please declare both as Tank types, plus the relation that links each chunk back to its manual.

## Type: `manual`

- Table: `manual`
- Nature: **original** (this is source data, not something Tank derives).
- Text field: `body` — this is the field holding the manual's main text.
- Attributes: one attribute, `title`, of type `string`. No closed vocabulary (no `values`) and no description needed.
- Identity: a manual is identified by its `title` field. There are no version fields — manuals aren't versioned in this declaration.
- No locator (manuals aren't located inside anything else), no vector config, no fulltext config, no description.

## Type: `chunk`

- Table: `chunk`
- Nature: **original**.
- Text field: `content` — the chunk's text content.
- Attributes: one attribute, `pos`, of type `int`. No closed vocabulary, no description. This is the chunk's position/order within its manual.
- Identity: none — don't declare an `id` block for chunk at all.
- Locator: chunks are located inside their source manual. Set the locator's source to `manual`, and order chunks by the `pos` attribute.
- No vector config, no fulltext config, no description.

## Relation: `chunk_of`

- Name: `chunk_of`
- From: `chunk`
- To: `manual`
- Kind: **field_link** — the link is expressed via a foreign-key-style field on the `chunk` side, not a separate join table. Do not set a `table` for this relation.
- Field: `manual` — this is the name of the field on `chunk` that holds the reference to its parent manual.
- No weight, no description.

## Scopes and freshness

No scopes and no freshness rules apply to this declaration — leave both empty.
