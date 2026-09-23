# Integration brief: product documentation (manuals + chunks)

We're onboarding our product documentation system onto Tank. The source data lives in
two tables: `manual` and `chunk`. Manuals are split into chunks (paragraphs/sections),
and each chunk belongs to exactly one manual. Please declare an ontology covering both
tables and the relationship between them.

## Type: `manual`

- Map this to a Tank type named `manual`, sourced from the `manual` table.
- This is original data (not machine-derived).
- The manual's identity is given by its `title` field — use that as the id, with no
  separate version fields.
- The full text of the manual lives in the `body` field; that's the text field for
  this type.
- Expose `title` as a queryable attribute as well (not just the id): it's a plain
  string with no closed set of allowed values.
- Manuals aren't chunks of anything else, so there's no locator to define here.
- No vector index, no fulltext index, and no description needed on this type — leave
  those out/empty.

## Type: `chunk`

- Map this to a Tank type named `chunk`, sourced from the `chunk` table.
- This is original data as well.
- Chunks don't have their own natural identity field — leave the id undefined for
  this type.
- The chunk's text lives in the `content` field; that's the text field.
- Each chunk carries a `pos` attribute — an integer — which gives its position/order
  within its parent manual. This has no closed vocabulary and needs no description.
- Chunks are units that live *inside* a source document, so they need a locator: the
  source is the `manual` type, and chunks are ordered within that source by their
  `pos` attribute.
- No vector index, no fulltext index, and no description needed on this type either.

## Relation: chunk → manual

- Declare a relation named `chunk_of` going from `chunk` to `manual`.
- This is a field-link relation (the link is carried directly by a field on the
  `chunk` table, not by a separate join table) — the field holding the reference is
  named `manual` on the `chunk` table.
- No weight and no description needed for this relation.

## Everything else

- No scopes are needed for this ontology.
- No freshness rules are needed for this ontology.

That's the complete declaration — two types (`manual`, `chunk`), one field-link
relation between them (`chunk_of`), no scopes, no freshness rules.
