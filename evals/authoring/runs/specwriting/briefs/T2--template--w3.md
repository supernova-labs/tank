## unit type: manual
table: manual
text mapping (the field holding the searchable content; this alone creates NO index): body
nature: original
stable identity fields: title
queryable attributes: title (string)
locator roles: none
full-text index: none
vector index: none

## unit type: chunk
table: chunk
text mapping (the field holding the searchable content; this alone creates NO index): content
nature: original
stable identity fields: none
queryable attributes: pos (int)
locator roles: source=manual, order=pos
full-text index: none
vector index: none

## relations
chunk_of: chunk -> manual, kind field_link, field manual, weight none

## scopes
none

## freshness
none
