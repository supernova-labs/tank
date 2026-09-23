# Integration brief: Helpdesk tickets

We need a Tank ontology declaration for our helpdesk system. There is exactly
one entity to declare for now: the support ticket.

## The table

Tickets live in a table called `ticket`. This is original, first-party data —
not something derived or computed from another source — so declare it with
the "original" nature.

## Identity

A ticket doesn't have a single surrogate ID column we want Tank to key on.
Instead, treat the combination of the ticket's `subject` and its `opened_at`
timestamp as what uniquely identifies a ticket record. There is no notion of
versioning for tickets (no version fields needed) — each ticket row is a
distinct, final record.

## The searchable text

The free-text content of a ticket — the actual body/description the
requester wrote — lives in a column called `body`. That's the field Tank
should treat as the type's main text content.

## Queryable attributes

Three fields should be exposed as queryable attributes:

1. **`subject`** — the ticket's subject line. It's a free-form string with no
   fixed set of allowed values.
2. **`priority`** — the ticket's priority level. This is a closed
   vocabulary: the only valid values are `p1`, `p2`, and `p3`. Nothing else
   should be accepted.
3. **`opened_at`** — the timestamp when the ticket was opened. This is a
   datetime field, not a string, and (as noted above) it doubles as part of
   the ticket's identity.

No other attributes are needed, and none of these three need a human-readable
description beyond their names — the names are self-explanatory.

## What doesn't apply here

- **Units locator**: tickets aren't chunked into sub-units (like paragraphs
  or sections) that need their own locator within the source — leave that
  unset.
- **Search indexes**: we don't have vector or full-text indexes configured
  on this table yet — leave both unset.
- **Relations**: there's nothing else to relate tickets to at this point —
  no other types are being declared, so no relations exist.
- **Scopes**: no access-control or partitioning scopes apply here.
- **Freshness**: no freshness/staleness policy is needed for this type.

## Summary

One type, `ticket`, sourced from the `ticket` table, original data, identified
by the pair (`subject`, `opened_at`), with `body` as its text field and three
attributes: `subject` (free string), `priority` (enum: p1/p2/p3), and
`opened_at` (datetime). Everything else — locator, vector, fulltext,
relations, scopes, freshness — is empty/unset for this declaration.
