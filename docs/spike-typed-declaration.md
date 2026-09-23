# Spike: typed declaration layer (classes) on top of the declarative `Ontology`

> Branch `spike/typed-declaration`, built on top of PR #20 (`feat/tank-0.1-validator`).
> Purpose: give D4 (issue #3, "where is the boundary between declarative and code?")
> empirical evidence before merging #20. Throwaway code; the decision is the deliverable.

## The question

PR #20 makes the consumer write one declarative object:

```python
ontology = Ontology(types=[UnitType("news", table="news", attrs=[Attr("title", "string"), ...])], ...)
```

The alternative on the table: the consumer writes **one class per unit type**, typed, usable
in the rest of the application, and Tank derives the declaration from the classes:

```python
class News(Unit, table="news", nature="original"):
    title: Annotated[str, Key()]
    body: Annotated[str, Text(), Searchable(analyzer="az_en", language="english")]
    published_at: Annotated[datetime, Key(), Ages("30d")]
    emb: Embedding[4] | None = None
    feed: Annotated[Link[Feed], Named("from_feed")]

class Mentions(Edge, src=News, dst=Entity):
    relevance: Annotated[float, Weighted()]

ontology = Ontology.of(News, Entity, Topic, Document, Feed, Mentions, About, Cites,
                       scopes=[Scope("entity", via="mentions")])
```

## Round 2: the "ideal model" — classes as the public API

After the first round (classes as an optional layer, equivalence proven) the branch was
taken one step further: **typed classes are the way to declare; the declarative
`Ontology` object is the internal representation** (what `Ontology.of` derives, what
`tank check` reads, what exports as JSON for the skill). The declarative objects still
exist and can be built programmatically, but README, fixtures and docs speak classes.

Final syntax (`tests/fixtures/news_mini/ontology_typed.py`, `README.md`):

```python
class News(Unit, table="news", nature="original"):
    title: Annotated[str, Key()]
    body: Annotated[str, Text(), Searchable(analyzer="az_en", language="english")]
    published_at: Annotated[datetime, Key(), Ages("30d")]
    emb: Annotated[Embedding[4], Embed(metric="cosine", model="bge-m3")] | None = None
    feed: Annotated[Link[Feed], Named("from_feed")]      # name defaults to the field name

class Note(Unit, table="note"):
    about: Link[Source, "Note"]                          # several targets; self-ref by name

    @rendered_text                                       # computed text → Rendered(method="card")
    def card(self) -> str: ...

class Mentions(Edge, src=News, dst=Entity):
    relevance: Annotated[float, Weighted()]

ontology = Ontology.of(News, Entity, Topic, Document, Feed, Mentions, About, Cites,
                       scopes=[Scope("entity", via="mentions")])
```

### Design changes from round 1 (each one closes a cost found in the spike)

| Change | Closes |
|---|---|
| No non-type strings inside subscripts: `Link[Feed]` only; relation name via `Named(...)`; metric/model via `Embed(...)` marker; `Embedding[dim]` only | Linters flagging `F821` on `Link[Feed, "from_feed"]` / `Embedding[4, "cosine"]`. Zero `noqa` in the fixture now |
| `Relation.to: str \| list[str]` in the IR, `Link[A, "B"]` / `dst=A \| B` in classes; `REL-002`/`REL-003` verify every declared target (`record<a\|b>`, `OUT a \| b`) | The vision's `Relation("mentions", "note", ["source", "note"])`, unexpressible in #20 |
| `@rendered_text` method → `UnitType.text = Rendered(method=...)`; `declared_fields()` ignores it | Computed text (entity card, fact sentence) had no home in the declarative object |
| `Text()` fields are not attrs; all other fields are, `Hidden()` opts out; record `id` skipped | The "which fields are attrs" decision, now explicit |
| Declaration modules must be pure (no connections, no settings) — documented rule | `tank check` in CI importing app code |
| `Unit`/`Edge` carry no CRUD | Tank drifting into an ORM |

### What did NOT change (deliberately left for the merge discussion)

- `_PosModel` positional args on `UnitType`/`Attr`/`Relation` are still there: all of PR #20's
  fixtures and tests use them. Once the declarative layer is internal they should go, but
  ripping them out on the spike would bury the comparison in mechanical churn.
- `notebooks/demo-tank-check.ipynb` still shows the declarative form.
- Verifiers per type (`QuoteMatch`, `Recompute`) are phase 4; the class form has the obvious
  home (a classmethod), nothing was built.

### Numbers after round 2

| | |
|---|---|
| Tests | 90 (67 from #20 untouched + 23 typed: equivalence, mapping rules, errors, rendered text, multi-target, 2 live-DB) |
| Lint / format | clean, no `noqa` in the typed fixture |
| Live check (SurrealDB 3.1.6) | typed `news_mini`: 27/27 same findings as declarative; DB and class sabotages fail with the same codes; multi-target `record<source\|note>` + `OUT source \| note` verified, sabotage → `REL-003` FAIL |
| Consumer lines, `news_mini` | 46 declarative → 33 typed |
| Framework code | `typed.py` ≈ 610 lines (a third of it docstrings); `ontology.py` +25 (Rendered, multi-target); `checks.py` +20 (multi-target REL) |

## Where the metaprogramming actually bit (round 1, kept for the record)

1. **pydantic class kwargs.** `class News(Unit, table="news")` works only if `Unit` overrides
   `__init_subclass__` to swallow the kwargs (object's rejects them) *and* consumes them in
   `__pydantic_init_subclass__`, which runs after `model_fields` exist. Solved once; invisible
   to the consumer.
2. **Markers inside unions.** `Embedding[4] | None` keeps its `Annotated` metadata nested
   under `Optional[...]`; pydantic does not hoist it into `FieldInfo.metadata`. The layer
   walks the annotation tree itself. The failure mode is silent (the embedding became an
   `array` attr on the first run), so the equivalence test is the permanent defense.
3. **Linters and strings in subscripts** — closed in round 2 by the syntax change.
4. **Parameterized fixtures are awkward in class form.** Test-suite only; a real project
   declares a static ontology. It does show that data is transformable and classes are not,
   which is the argument for keeping the declarative object as the internal representation.

## Recommendation

Classes as the public API, the declarative object as the internal representation — as
built on this branch. For PR #20: merge the validator, then land this branch's typed layer
(with README/fixtures/notebook in class form and positional args removed) **before** any
0.1 tag, so the first thing a consumer or the skill sees is the class form. The one thing
to confirm with the team first: whether the next consumers (Nord, Smart Fit) have or want a
pydantic domain model — if not, the declarative form must stay documented as an escape hatch.

## How to reproduce

```bash
git checkout spike/typed-declaration
uv sync
TANK_TEST_URL=http://127.0.0.1:8019 uv run pytest -q            # 90 passed
uv run tank check --ontology tests/fixtures/news_mini/ontology_typed.py \
    --url http://127.0.0.1:8019 --ns <ns> --db <db-seeded-with-news_mini>
```
