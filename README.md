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

0.1 ships the first piece: **ontology as typed code + deterministic checking against SurrealDB** — no LLM involved, CI-ready. This is the *validator milestone* of the first phase; the second half (the skill that lets an agent write access functions reading only the ontology) comes next.

**1. Declare your ontology** — one class per unit type, one per edge table (`ontology.py` in your project, kept free of database connections and settings):

```python
from datetime import datetime
from typing import Annotated, Literal

from tank import Ages, Edge, Embedding, Key, Link, Ontology, Searchable, Text, Unit, Weighted


class Agency(Unit, table="agency"):
    acronym: str


class Report(Unit, table="technical_assessment", nature="original"):  # YOUR table; Tank never writes to it
    code: Annotated[str, Key()]                       # stable identity
    body_text: Annotated[str, Text(), Searchable(analyzer="az_en")]
    status: Literal["current", "revoked"]             # closed vocabulary, verified by sampling
    issued_at: Annotated[datetime, Ages("365d")]      # freshness signal
    emb: Embedding[1536] | None = None                # ⇒ an HNSW index of DIMENSION 1536 must exist
    agency: Link[Agency]                              # record link ⇒ field_link relation "agency"


class Supersedes(Edge, src=Report, dst=Report):       # RELATE edge table "supersedes"
    extent: Annotated[float, Weighted(range=(0.0, 1.0))]


ontology = Ontology.of(Agency, Report, Supersedes, name="assessments", version="0.1.0")
```

`name` and `version` are required and have no default: they are the human half
of the stamp that says *which* declaration a later observation was made against.
`ontology.stamp()` pairs them with a digest of the declaration itself, so
reordering your classes for readability does not change the identity, and
editing one without bumping `version` does not go unnoticed.

The classes are plain pydantic models: `Report(**row)` parses a row from the database, access tools can return `list[Report]`, and renaming a field renames the declaration — there is no second copy to drift. Every field is a queryable attr unless it is a link, an embedding, a `Text()` field or marked `Hidden()`. Computed text (an entity card, a fact sentence) is a method decorated with `@rendered_text`.

`Ontology.of(...)` derives the declarative representation (`UnitType`, `Relation`, …) that `tank check` validates and that exports as JSON for the agent skill. An internally inconsistent ontology (a link to a class you did not pass, a scope without its relation, two `Searchable()` fields…) **blows up at import time** — the build breaks before any database connection exists.

**2. Run the check:**

```bash
uv run tank check --ontology ontology.py --url http://127.0.0.1:8000 --ns my_ns --db my_db
```

The report validates the database against the declaration — does the table exist? do declared fields have a `DEFINE FIELD` (or, without one, are they present in sampled rows)? does the declared value vocabulary match the data? does the edge have the declared direction? does the vector index exist with the right dimension and metric? — with four states (`PASS`/`FAIL`/`WARN`/`VACUOUS` — an empty table never passes silently), a header naming the exact environment validated, and a fixed section listing what is **not** verified. A non-zero exit code breaks CI; `--strict` promotes warnings to errors; `--json` for machines.

## Install

```bash
uv add git+https://github.com/supernova-labs/tank
```

Requires Python ≥ 3.11. Development: `uv sync`, then `uv run pytest` (integration tests need a local SurrealDB at `TANK_TEST_URL`; without one they skip). A runnable demo lives in [`notebooks/demo-tank-check.ipynb`](notebooks/demo-tank-check.ipynb).

## License

[MIT](LICENSE)
