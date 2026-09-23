# Integration brief: helpdesk tickets

We need a Tank ontology declaration for our helpdesk system's `ticket` table. This is the only type we need to declare for now — no other types, no relations between types, no scopes, and no freshness rules.

## The type

- Name the type `ticket`, sourced from the `ticket` table.
- This is original data — it comes directly from our own database, not something derived or computed from another source.

## Identity

A ticket is identified by the combination of its `subject` and its `opened_at` timestamp. There are no version fields — we don't track revisions of a ticket's identity.

## Text field

The body of the ticket (the field literally called `body`) is the text content Tank should treat as this type's primary text.

## Attributes

Three attributes, all queryable:

1. **subject** — a plain string. No closed vocabulary (it's free text), no description needed.
2. **priority** — a string restricted to exactly three values: `p1`, `p2`, `p3`. No description needed.
3. **opened_at** — a datetime field. No closed vocabulary, no description needed.

## Things that don't apply here

- No locator — we're not pointing into a larger source document, so leave this unset.
- No vector index and no fulltext index configured for this type.
- No top-level description for the type itself.
- No relations, scopes, or freshness entries anywhere in the declaration — this is a single, standalone type.

That's the whole declaration: one original type (`ticket`) with the identity, text, and three attributes described above, and nothing else populated.
