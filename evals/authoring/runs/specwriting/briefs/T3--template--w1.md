## unit type: author
table: author
text mapping (the field holding the searchable content; this alone creates NO index): none
nature: original
stable identity fields: none
queryable attributes: name (string)
locator roles: none
full-text index: none
vector index: none

## unit type: kb_article
table: kb_article
text mapping (the field holding the searchable content; this alone creates NO index): body
nature: original
stable identity fields: slug
queryable attributes: slug (string), status (string) [closed vocabulary: draft, published, archived], updated_at (datetime)
locator roles: none
full-text index: body + analyzer az_kb + language english
vector index: emb + 8 dimensions + metric cosine

## unit type: summary
table: summary
text mapping (the field holding the searchable content; this alone creates NO index): text
nature: derived
stable identity fields: none
queryable attributes: created_at (datetime)
locator roles: none
full-text index: none
vector index: none

## relations
summarizes: summary -> kb_article, kind field_link, field article, weight none
written_by: kb_article -> author, kind edge, field n/a, weight share (higher is better)

## scopes
author via written_by

## freshness
kb_article ages on updated_at, decay 45d
