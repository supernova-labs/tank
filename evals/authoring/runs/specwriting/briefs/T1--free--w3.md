# Ontology brief: Helpdesk tickets

We need a Tank ontology declaration for our helpdesk system, covering the single `ticket` table. Here's everything you need to know about the data.

## The table

The source table is called `ticket`. Each row is an original record — it's captured directly from the helpdesk system, not derived or computed from other data.

## Identity

Tickets don't have a single dedicated ID column we want Tank to key on. Instead, treat the combination of the ticket's `subject` and its `opened_at` timestamp as what uniquely identifies a ticket for Tank's purposes. There's no versioning concept for tickets — we don't track revisions of the same logical ticket, so there's nothing to add on that front.

## The searchable text

The free-text content Tank should treat as the ticket's body of text is the `body` column — that's where the actual description/content of the ticket lives.

## Fields to expose

Three fields should be queryable as attributes:

- **`subject`** — the ticket's subject line, a free-form string. There's no fixed set of values here — subjects vary ticket to ticket, so don't constrain it to a vocabulary.
- **`priority`** — a string field, but this one *does* have a closed set of allowed values: `p1`, `p2`, and `p3`. Nothing outside that set should be considered valid.
- **`opened_at`** — a datetime field recording when the ticket was opened. Like `subject`, this has no closed vocabulary — it's just a timestamp.

None of these three fields need a human-readable description beyond their name; the names are self-explanatory enough that we're not attaching extra descriptive text to any of them.

## What doesn't apply here

A few things Tank supports aren't needed for this table:

- No locator — we're not telling Tank how to find units of text inside a larger unit (e.g., chunk/passage locations); tickets don't need that.
- No vector index and no fulltext index — we are not configuring any search index on this type for now.
- No description at the type level either — just the fields above.

## Beyond the ticket type

This is the only type we're declaring right now:

- No relations to other types — we're not linking `ticket` to anything else in this pass.
- No scopes defined.
- No freshness policies defined.

That's the complete picture — a single, original `ticket` type with `subject` + `opened_at` as its identity, `body` as its text, and three attributes (`subject`, `priority` restricted to p1/p2/p3, and `opened_at`), nothing else configured.
