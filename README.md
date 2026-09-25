# Tank

A framework to make your content accessible to agents — and prove it is being used well.

Tank does not ship a ready-made pipeline: the pipeline is yours. It offers opinionated contracts (an ontology declared in code, access tools as decorated functions, usage and citation records) that your project implements — and by implementing them gains capabilities: search that respects your ontology, citable and versioned evidence, optional verification, and — most importantly — analytics on how agents access your data and what actually proved useful. An async Python package, SurrealDB-first, in the same mold as [content-core](https://github.com/lfnovo/content-core), [esperanto](https://github.com/lfnovo/esperanto) and [ai-prompter](https://github.com/lfnovo/ai-prompter).

Open source since day zero.

## Documents

> The vision documents below are currently in Portuguese; English translations are planned.

- [`docs/rag-vision.md`](docs/rag-vision.md) — the vision document (story + technical part). The source of the thesis.
- [`docs/rag-vision.v1-retrieval-lib.md`](docs/rag-vision.v1-retrieval-lib.md) — the previous version (a retrieval library), kept for the record.
- [`docs/rag-lib-requirements.md`](docs/rag-lib-requirements.md), [`docs/rag-references.md`](docs/rag-references.md), [`docs/rag-references-libs.md`](docs/rag-references-libs.md), [`docs/rag-references-research.md`](docs/rag-references-research.md) — requirements and reference research.
- [`docs/checks.md`](docs/checks.md) — reference for every `tank check` code (English).

## What comes first

1. Contracts + ontology + validator — declare, validate, inspect.
2. Usage and citation records + basic analytics.
3. Access tools (`@access_tool`) + registry + adapters (LangChain, MCP).

The two real challenges: **indexing and ontology** (what the library validates × what the project declares) and the **search protocol**. Readiness test: "use the Tank skill on this ontology and write a function that finds news items from an entity" — the agent has to pull it off.

## Tank 0.1 — the validator (`tank check`)

0.1 ships the first piece: **ontology as code + deterministic checking against SurrealDB** — no LLM involved, CI-ready. This is the *validator milestone* of the first phase; the second half (the skill that lets an agent write access functions reading only the ontology) comes next.

**1. Declare your ontology** (`ontology.py` in your project, kept free of database connections and settings):

```python
from tank import Attr, Ontology, Relation, StableId, UnitType

ontology = Ontology(
    name="assessments",   # who this declaration is
    version="0.1.0",      # and which revision of it
    types=[
        UnitType(
            "report",
            table="technical_assessment",  # YOUR table; Tank never writes to it
            id=StableId.of("code"),
            text="body_text",
            attrs=[
                Attr("code", "string"),
                Attr("status", "string", values=["current", "revoked"]),
                # Opaque codes: declare what they MEAN, not just which exist.
                # An agent can already discover the list from the data; in an
                # ablation, the bare list cost six queries to decode where the
                # mapping cost one.
                Attr("priority", "string", values={"p1": "high", "p2": "medium", "p3": "low"}),
                Attr("issued_at", "datetime"),
            ],
        ),
        UnitType("agency", table="agency", attrs=[Attr("acronym", "string")]),
    ],
    relations=[
        Relation("agency", "report", "agency", kind="field_link", field="agency"),
    ],
)
```

`name` and `version` are required and have no default: they are the human half
of the stamp that says *which* declaration a later observation was made against.
`ontology.stamp()` pairs them with a digest of the declaration itself, so
reordering your types for readability does not change the identity, and editing
one without bumping `version` does not go unnoticed.

An internally inconsistent ontology (a relation pointing at an undeclared type, a scope without its relation, a vector without a dimension…) **blows up at import time** with every `ONT-*` code at once — the build breaks before any database connection exists.

<details>
<summary>The same declaration as typed classes (<code>tank.typed</code>, opt-in)</summary>

If your project already keeps pydantic models of its domain, the declaration can
live on them instead, and there is no second copy to drift:

```python
from datetime import datetime
from typing import Annotated, Literal

from tank import Ontology
from tank.typed import Key, Link, Text, Unit, Values


class Agency(Unit, table="agency"):
    acronym: str


class Report(Unit, table="technical_assessment", nature="original"):
    code: Annotated[str, Key()]
    body_text: Annotated[str, Text()]
    status: Literal["current", "revoked"]
    priority: Annotated[
        Literal["p1", "p2", "p3"],
        Values({"p1": "high", "p2": "medium", "p3": "low"}),
    ]
    issued_at: datetime
    agency: Link[Agency]


ontology = Ontology.of(Agency, Report, name="assessments", version="0.1.0")
```

`Ontology.of(...)` derives exactly the declarative form above, and `tests/test_typed.py`
holds the two to that. The markers are imported from `tank.typed` rather than
from `tank`: names like `Text`, `Key` and `Link` collide with half the ecosystem
at the top level, and a name in `__all__` is a promise.

Which form is better is an open question with evidence on one side only so far:
in the authoring ablation the declarative form won first-try accuracy in all
three rounds (100% against 85% in the round with disambiguated specs). That
measured an *agent writing* a declaration, not a *human maintaining* one
alongside a domain model, which is the case the typed form is for.

</details>

**2. Run the check:**

```bash
uv run tank check --ontology ontology.py --url http://127.0.0.1:8000 --ns my_ns --db my_db
```

The report validates the database against the declaration — does the table exist? do declared fields have a `DEFINE FIELD` (or, without one, are they present in sampled rows)? does the declared value vocabulary match the data? does the edge have the declared direction? does the vector index exist with the right dimension and metric? — with four states (`PASS`/`FAIL`/`WARN`/`VACUOUS` — an empty table never passes silently), a header naming the exact environment validated, and a fixed section listing what is **not** verified. A non-zero exit code breaks CI; `--strict` promotes warnings to errors; `--json` for machines.

## Tank 0.2 — the access trail (`access_tool`)

0.2 records how agents actually use what you declared. An access tool is an
async function you decorate; Tank opens and closes the boundary of the call,
measures it, classifies any exception **without altering it**, and writes one
event per call plus one row per unit returned.

```python
from tank.access import Candidate, Registry, SurrealSink, refs_from, session

registry = Registry(ontology)          # binds at import, blind to the tenant


@registry.access_tool(
    name="news_by_entity",             # a join key: explicit, never __name__
    version="1.0.0",                   # declared, never a hash of the body
    returns=Candidate,                 # Ref | Candidate | Evidence
    via="own",                         # "own" | "gateway" — no default
    scope="entity",                    # WHICH kind of cut
    scope_from="entity_id",            # and which argument carries its value
)
async def news_by_entity(entity_id: str, limit: int = 20) -> list[Candidate]:
    rows = await your_own_query(...)   # the SQL is 100% yours
    return refs_from(rows, type="news", stage=Candidate)


# the tenant binds separately, at the call
async with session(registry, SurrealSink(conn), ns="acme", db="newsroom",
                   run_id="conv-7d2f/msg-3"):
    await news_by_entity("entity:e1")
```

Apply the schema first — `src/tank/migrations/0001_access.surql` — because the
event's core columns are non-`option` with no backfill, and the sink refuses to
write into a database that has not been migrated rather than letting SurrealDB
fabricate a schemaless table on the first insert.

**The rule the decorator runs on is "marked, never silenced":**

- **Your exception is yours.** There is no `swallow=True`, not even opt-in. It
  propagates as the same object, and the event records its class and type.
- **A failure of the instrument is not a failure of your call.** If the event
  cannot be written, that is swallowed, logged and counted; your result returns
  untouched.
- **Absence is always named.** No field is left empty without the event saying
  why. A tool that declares a scope and receives no value for it records
  `unbound`, which is a different fact from `undeclared` — one is an
  instrumentation defect and the other is how the tool is meant to work.

That last rule is the whole design. Asking "was the scope respected?" over four
events where only one declared a scope answers `UNOBSERVABLE, 3 of 4`, with the
reason per event. The same question asked of a nullable column answers `4 of 4`.

**What 0.2 does not do yet:** the gateway that reads the query plan (so
`capture_mode` is `direct` and `obs.plan` says `below_mode` on every event),
`tank migrate`, the analytics command, and citation records — `use_link` and
`record_usage` are 0.3, where `returned` will be *derived* from the trail rather
than self-reported.

## Install

```bash
uv add git+https://github.com/supernova-labs/tank
```

Requires Python ≥ 3.11. Development: `uv sync`, then `uv run pytest` (integration tests need a local SurrealDB at `TANK_TEST_URL`; without one they skip). A runnable demo lives in [`notebooks/demo-tank-check.ipynb`](notebooks/demo-tank-check.ipynb).

## License

[MIT](LICENSE)
