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

0.1 ships the first piece: **ontology as Pydantic code + deterministic checking against SurrealDB** — no LLM involved, CI-ready. This is the *validator milestone* of the first phase; the second half (the skill that lets an agent write access functions reading only the ontology) comes next.

**1. Declare your ontology** (`ontology.py` in your project):

```python
from tank import Attr, Ontology, StableId, UnitType

ontology = Ontology(
    types=[
        UnitType(
            "report",
            table="technical_assessment",  # YOUR table; Tank never writes to it
            id=StableId.of("code"),
            text="body_text",
            attrs=[
                Attr("status", "string", values=["current", "revoked"]),
                Attr("issued_at", "datetime"),
            ],
        ),
    ],
)
```

An internally inconsistent ontology (a relation pointing at an undeclared type, a scope without its relation, a vector without a dimension…) **blows up at import time** with every `ONT-*` code at once — the build breaks before any database connection exists.

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
