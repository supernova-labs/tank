"""Task briefs for the authoring eval.

Deliberately prescriptive: they name every type, table, field and role, so the
gold IR is unique and the eval measures the API's ergonomics — how faithfully
and cheaply an agent translates spec -> declaration — not the agent's domain
modelling judgement.
"""

TASKS = {
    1: {
        "title": "one unit type",
        "brief": """\
Project: a helpdesk. Declare ONE findable type:

- `ticket`, stored in table `ticket`.
- Its searchable text lives in the field `body`.
- Epistemic nature: original.
- Stable identity is derived from the fields `subject` and `opened_at` (in this order).
- Queryable attributes: `subject` (string), `priority` (string, closed vocabulary:
  `p1`, `p2`, `p3`), `opened_at` (datetime).""",
    },
    2: {
        "title": "chunks, locator and field link",
        "brief": """\
Project: product documentation. Declare TWO findable types and their connection:

- `manual`, table `manual`: searchable text in field `body`; stable identity from the
  field `title`; queryable attribute `title` (string).
- `chunk`, table `chunk`: searchable text in field `content`; queryable attribute
  `pos` (int).
- Every chunk points at its manual through the record field `manual` on the chunk
  table. That connection is a relation named `chunk_of`, going from `chunk` to `manual`.
- The chunk's locator: the role `source` is played by the field `manual`; the role
  `order` is played by the field `pos`.""",
    },
    3: {
        "title": "the full surface",
        "brief": """\
Project: a knowledge base. Declare THREE findable types, two relations, one scope and
one freshness rule:

- `author`, table `author`: queryable attribute `name` (string). No text field, no
  stable id.
- `kb_article`, table `kb_article`: nature original; searchable text in field `body`;
  stable identity from the field `slug`; queryable attributes `slug` (string),
  `status` (string, closed vocabulary: `draft`, `published`, `archived`) and
  `updated_at` (datetime). Vector search on field `emb`, 8 dimensions, cosine metric.
  Full-text search on field `body` with analyzer `az_kb`, language `english`.
- `summary`, table `summary`: nature derived; searchable text in field `text`;
  queryable attribute `created_at` (datetime).
- Relation `summarizes`: every summary points at its article through the record field
  `article` on the summary table (from `summary` to `kb_article`).
- Relation `written_by`: an edge from `kb_article` to `author` (edge table has the
  relation's name) carrying a ranking weight stored in the edge field `share`
  (higher is better).
- Scope `author`, reached via the relation `written_by`.
- Freshness: `kb_article` ages on the field `updated_at` with decay `45d`.""",
    },
    4: {
        "title": "maintenance: extend an existing declaration",
        "brief": """\
The project already declares its ontology — the starter file given above contains it.
Your submission must contain everything the starter declares, semantically unchanged,
PLUS:

- A new type `faq`, table `faq`: searchable text in field `answer`; stable identity
  from the field `question`; queryable attributes `question` (string) and `tag`
  (string, closed vocabulary: `howto`, `billing`, `bug`).
- A new relation `covers_manual`: an edge from `faq` to `manual` (edge table has the
  relation's name), no weight.""",
    },
}
