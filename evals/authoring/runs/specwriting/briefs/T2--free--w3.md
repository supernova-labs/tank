# Ontology brief: product documentation (manuals + chunks)

We're onboarding a documentation corpus. Manuals get split into chunks for
retrieval, and we need Tank's ontology to describe both tables. Here's
everything you need.

## Source tables

**`manual`** — one row per manual.
- `body`: the full text of the manual.
- `title`: the manual's title. This is also what identifies a manual — there's
  no separate numeric/UUID id field we want Tank to key on; `title` is the
  business identity.

**`chunk`** — one row per chunk of a manual.
- `content`: the chunk's text — this is the field retrieval should treat as
  the searchable text.
- `pos`: an integer giving the chunk's position/order within its parent
  manual (0, 1, 2, ...).
- `manual`: a reference field on the chunk row pointing back to the manual it
  belongs to.

Chunks don't have their own natural business key — don't declare an identity
for them at all, just leave that out.

## What to declare

Both `manual` and `chunk` are original data (not derived from something
else), sourced straight from their respective tables of the same name.

For `manual`:
- Text field: `body`.
- Identity: keyed on `title` (no versioning fields).
- Queryable attribute: `title`, typed as a plain string. No closed vocabulary,
  no description needed.

For `chunk`:
- Text field: `content`.
- No identity block (see above).
- Queryable attribute: `pos`, typed as an integer. No closed vocabulary, no
  description needed.
- Locator: chunks are located *within* their source manual, ordered by the
  `pos` attribute. The source for this locator is the `manual` type.

Neither type needs a vector index, a fulltext index, or a description — leave
those out.

## Relation

Declare one relation, `chunk_of`, from `chunk` to `manual`. It's a direct
field link (not a join table): the link lives in the `manual` field already
present on the `chunk` row — that's the field Tank should follow to resolve
the relation. No weight, no description needed.

## Scopes / freshness

Nothing to declare here — no access scopes and no freshness/staleness rules
apply to this corpus.
