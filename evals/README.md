# evals

Two harnesses that measure the same claim from opposite ends: **does declaring
an ontology change what an agent can do with a database?**

| | subject | asks |
|---|---|---|
| [`ablation/`](ablation/README.md) | an agent **querying** | with which parts of the declaration removed does it still answer correctly, and at what query cost? |
| [`authoring/`](authoring/README.md) | an agent **writing** the declaration | given a spec, does it produce the right ontology on the first try? |

Both write a log per run, and **every score comes from that log, never from the
agent's self-report**. That rule paid for itself: in the ablation, 61 of 336
runs under-reported the queries they had made and none over-reported, so a
scorer trusting the agent would have credited work that did not happen.

## Why `runs/` and `results/` are versioned

They are the output of 624 paid agent runs. They cannot be regenerated for free,
and a harness without them is not runnable — by anyone, including CI. Together
they are 11 MB of JSON and Python that pack to well under 1 MB.

`runs/*/submissions/*.py` in particular are **experiment data, not project
code**: they are what agents actually wrote under the prompts of their round.
They are never edited to satisfy a later version of the library. When the
library changes under them, the judge adapts and records that it did.

## The ablation corpus, and what it does not exercise

`ablation/runs/*/log/*.jsonl` holds **1,708 statements that real agents wrote**
against a real SurrealDB — the only record this project has of how agents phrase
SurrealQL when nobody is watching. It is the input to the offline benches
(`b2_plan_coverage.py`, `b2b_index_resolution.py`), which replay it without
spending a token.

Measured over those 1,708 lines:

- 1,693 succeeded, **15 failed** — anything replaying the corpus has to filter
  on `ok`, or it will produce access records for queries that returned nothing
  to anyone.
- **0 statements define or use an index.** `b2b_index_resolution.py` exists
  because of this hole and seeds its own indexes.
- **2 use full-text (`@@`), 0 use vector KNN (`<|…|>`).** Both paths are
  effectively unmeasured here.
- Every line carries `allow_introspect`, so tier evasion is detectable from the
  log rather than from what the agent claimed.

What the corpus contains no examples of at all: a declared access tool, a scope,
a stage, a refusal. Any conclusion about those is not supported by this data.

## Running them

Neither harness runs under `pytest` — they spend money and need a server. See
the per-harness README. Two paths are environment-configurable rather than
hardcoded: `TANK_SURREAL_BINARY` (the 3.x binary the offline benches start) and
`TANK_SPIKE_WORKTREE` (the checkout the typed arm is judged against).
