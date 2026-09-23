# Tank ontology brief: knowledge base (articles, authors, summaries)

We need a Tank ontology declaration for our knowledge base project. The database has three tables: `author`, `kb_article`, and `summary`. Below is everything you need to map them into Tank's vocabulary.

## Types

### `author`
- Maps to table `author`.
- Nature: **original** (authored directly by humans, not machine-derived).
- No identity spec needed — leave `id` unset.
- No primary text field — leave `text` unset.
- No vector index, no fulltext index, no description.
- Attributes:
  - `name` — type `string`. No closed vocabulary, no description.

### `kb_article`
- Maps to table `kb_article`.
- Nature: **original**.
- Identity: the natural key is the `slug` field. There's no versioning scheme for articles (no version fields).
- Primary text field: `body` — this is the field Tank should treat as the article's main text content.
- Attributes:
  - `slug` — type `string`.
  - `status` — type `string`, restricted to a closed vocabulary: `draft`, `published`, `archived`.
  - `updated_at` — type `datetime`.
- Vector index: articles have an embedding stored in the `emb` field, dimension **8**, using **cosine** similarity. We don't track which model produced the embeddings, so leave `model` unset.
- Fulltext index: built on the `body` field, using the `az_kb` analyzer, language **english**.
- No description needed.

### `summary`
- Maps to table `summary`.
- Nature: **derived** (these are machine-written summaries, not original content).
- No identity spec needed — leave `id` unset.
- Primary text field: `text` — this holds the summary's textual content.
- No vector index, no fulltext index, no description.
- Attributes:
  - `created_at` — type `datetime`.

## Relations

### `summarizes`
- From `summary` to `kb_article`.
- Kind: **field_link** — the link is a plain foreign key, not a join table.
- The foreign key field is `article` on the `summary` table (i.e., `summary.article` points at the `kb_article` it summarizes).
- No table, no weight, no description needed for this relation.

### `written_by`
- From `kb_article` to `author`.
- Kind: **edge** — this relationship goes through its own join table, `written_by` (supporting many-to-many between articles and authors).
- This edge carries a weight: the `share` field on the join table, where a **higher** value is better (interpreted as e.g. the author's share/credit on the article). No fixed numeric range for this weight.
- No description needed.

## Scopes

We need one scope named `author`, reached via the `written_by` relation. This lets queries be scoped down to a specific author's contributions. No description needed.

## Freshness

Articles go stale over time: define freshness for the `kb_article` type keyed on its `updated_at` field, with a decay of **45 days**.

That's the full ontology — three types, two relations, one scope, one freshness rule. Nothing else needs to be declared.
