# Tank ontology brief — knowledge base project

We need a Tank ontology for our knowledge base: articles, their authors, and
machine-written summaries of those articles. Below is everything you need to
declare the three types, their relationships, one scope, and one freshness
rule.

## Type: `author`

- Maps to the `author` table.
- Nature: **original** (human-authored data, not machine-derived).
- No identity (id) fields need to be declared for this type.
- No text field — authors have no body of text to index for search.
- One attribute:
  - `name` — string. No closed vocabulary, no description needed.
- No locator, no vector index, no fulltext index.

## Type: `kb_article`

- Maps to the `kb_article` table.
- Nature: **original**.
- Identity: the natural key is the single field `slug`. There are no
  version fields.
- Text field: `body` — this is the field holding the article's main text.
- Attributes:
  - `slug` — string (this doubles as the identity field above).
  - `status` — string, restricted to a closed vocabulary of exactly three
    values: `draft`, `published`, `archived`.
  - `updated_at` — datetime.
- No locator needed.
- Vector index: field `emb`, dimensionality 8, metric `cosine`. No
  particular embedding model needs to be recorded.
- Fulltext index: field `body`, analyzer named `az_kb`, language `english`.

## Type: `summary`

- Maps to the `summary` table.
- Nature: **derived** (these are machine-generated, not authored by a
  person).
- No identity fields need to be declared for this type.
- Text field: `text` — this is the field holding the summary's generated
  text.
- One attribute:
  - `created_at` — datetime.
- No locator, no vector index, no fulltext index.

## Relations

1. **`summarizes`**: from `summary` to `kb_article`. This is a direct field
   link, not a join table — the `summary` table has a field named `article`
   that points at the `kb_article` it summarizes. No weight.

2. **`written_by`**: from `kb_article` to `author`. This is an edge backed
   by its own join table, named `written_by` (same name as the relation).
   The edge carries a weight: the field `share` on that join table, where a
   **higher** value means a stronger/better match (i.e. `higher_is_better`
   is true). No fixed numeric range needs to be declared for that weight.

## Scopes

- One scope named `author`, reached via the `written_by` relation. This
  lets queries be scoped down to "content written by a given author."

## Freshness

- `kb_article` documents go stale based on their `updated_at` field, with a
  decay window of **45 days**.

Nothing else needs to be declared — no other types, relations, scopes, or
freshness rules belong in this ontology.
