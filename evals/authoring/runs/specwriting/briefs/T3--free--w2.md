# Integration brief: knowledge base ontology for Tank

We're wiring up Tank for a knowledge base app: articles, their authors, and
machine-written summaries of articles. Below is everything you need to write
the ontology declaration.

## Types

### `author`
- Backed by the `author` table.
- Nature: **original** (human-authored source data, not machine-derived).
- No identity spec needed — leave `id` unset.
- No primary text field for this type — leave `text` unset.
- One attribute:
  - `name` — string. No closed vocabulary, no description needed.
- No locator, no vector index, no fulltext index on this type.

### `kb_article`
- Backed by the `kb_article` table.
- Nature: **original**.
- Identity: identified by its `slug` field. No versioning fields.
- Text field: `body` (this is the field holding the article's main text).
- Attributes:
  - `slug` — string.
  - `status` — string, restricted to a closed vocabulary of exactly
    `draft`, `published`, `archived`.
  - `updated_at` — datetime.
- No locator (this type isn't a sub-unit of something else).
- Vector index: field `emb`, dimensionality 8, cosine similarity metric. No
  model name to record.
- Fulltext index: field `body`, analyzer `az_kb`, language `english`.

### `summary`
- Backed by the `summary` table.
- Nature: **derived** (machine-written, not original source content).
- No identity spec — leave `id` unset.
- Text field: `text` (holds the summary's text content).
- One attribute:
  - `created_at` — datetime.
- No locator, no vector index, no fulltext index on this type.

## Relations

### `summarizes`
- From `summary` to `kb_article`.
- Kind: **field_link** — the link lives as a field on the `summary` row
  itself (not a separate join table), specifically the `summary.article`
  field pointing at the article it summarizes.
- No weight, no separate table.

### `written_by`
- From `kb_article` to `author`.
- Kind: **edge** — backed by its own join table, `written_by` (not a plain
  field reference).
- Weighted: the edge table carries a `share` field expressing each author's
  share of credit for the article, and higher values of `share` are better
  (i.e., `higher_is_better` is true). No explicit numeric range to record for
  this weight.

## Scopes

- One scope named `author`, reached via the `written_by` relation. This lets
  queries be scoped down to "everything written by a given author" by
  traversing `written_by`.

## Freshness

- One freshness rule, on `kb_article`: use its `updated_at` field for
  recency, with a decay half-life (or equivalent decay window) of 45 days.
  No freshness rules apply to `author` or `summary`.

## Everything not mentioned

Any field, option, or descriptor not called out above (extra descriptions on
types/attrs/relations/scopes, a model name on the vector index, a numeric
range on the `written_by` weight, locators, etc.) should be left unset —
there's nothing further to encode for this ontology.
