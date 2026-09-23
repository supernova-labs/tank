# Ontology ablation eval

Does each field of the ontology actually change agent behavior at retrieval time?
`tank check` validates *consistency*; this harness validates *usefulness* — an
ablation study: agents get variants of the same ontology with one component
removed, solve the same tasks over the same data, and the matrix shows which
component's removal hurts (success or cost) in its own task category.

Outcome levels per component: **necessary** (success drops), **saves cost**
(success holds, queries/turns rise), **inert** (no measurable difference →
candidate to leave the model).

## Pieces

Each round has a **spec module** (`spec_round1.py`, `spec_round2.py`) exposing
`TASKS` and `variants()`; everything else is round-agnostic:

- `spec_round1.py` (+ `fixtures/newsroom.surql`, `ontology_full.py`, `tasks.py`) —
  round 1: 6 variants (`full`, `no_values`, `no_locator`, `no_nature`,
  `minimal`, `none`), small dataset. Result: success at ceiling; only cost
  (query count) discriminated — the whole ontology saves 2–5 queries, but
  single components were compensable.
- `spec_round2.py` (+ generated `fixtures/newsroom2.surql`) — hardened after
  round 1: opaque vocabulary codes (the semantics→code mapping is undeclarable
  in today's model — the extra `full_plus` variant carries it in descriptions),
  order field `cut` against a contiguous `seq` decoy, `factbox`
  (original-but-machine-sounding) vs `brief` (derived-but-human-sounding),
  4x more rows so full dumps hit output truncation.
- `gen_runs.py` — builds variants by *deleting keys* from the JSON export,
  writes one prompt file per run and a `manifest.json`
- `query.py` — read-only SurrealQL gateway for agents; logs every invocation
  (the scorer trusts the log, not the agent's self-report); enforces the
  no-introspection condition
- `score.py` — scores raw agent outputs against gold, aggregates the
  variant × condition × category matrix into `results/<round>.md`

## Running a round

```bash
surreal start --user root --pass root --bind 127.0.0.1:8022 memory   # keep running
uv run python evals/ablation/spec_round2.py                          # (re)write the fixture
curl -s -X POST http://127.0.0.1:8022/sql -u root:root \
  -H 'surreal-ns: tank_eval' -H 'surreal-db: newsroom' -H 'Accept: application/json' \
  --data-binary @evals/ablation/fixtures/newsroom2.surql

uv run python evals/ablation/gen_runs.py --round round2 --spec spec_round2 --reps 3
# run one agent per manifest entry (any orchestrator); each agent reads its
# prompt file and returns the structured output described in it; collect the
# outputs into results/round2_raw.json
uv run python evals/ablation/score.py --raw evals/ablation/results/round2_raw.json \
  --round round2 --spec spec_round2
```

Conditions: `intro` (schema introspection allowed) and `nointro` (INFO/DESCRIBE
refused). The difference between them is the measure of how much the ontology
*saves* — information the agent could reconstruct, at a cost.

## Findings (rounds 1–2, 2026-09-17, Sonnet agents, k=3)

Per component, against the three-outcome rubric:

- **`Locator.order` — necessary.** With two plausible ordering fields on the
  table (`cut` char offsets vs a contiguous `seq` ingestion decoy), removing the
  locator took in-order retrieval from 6/6 to 0/6–1/6. Agents pick the field
  that *looks* like an order. Introspection does not rescue it (INFO says
  nothing about which field orders text).
- **`Attr.values` as a bare list — near-inert; the *mapping* is what matters.**
  With opaque codes, `full` (list only) matched `no_values` (5–6/6 at ~6
  queries, one outright wrong-cluster answer): agents can rediscover the list
  from the data, so the list itself adds almost nothing. `full_plus` (code →
  meaning in the description) went 6/6 at 1 query. → model change: `Attr.values`
  now accepts `dict[str, str]` (code → meaning).
- **`nature` — cost saver.** Agents recovered original/derived without it
  (via link topology and text style) but at ~2x the queries; table names
  actively mislead in both directions (`brief` derived, `factbox` original).
- **Ontology as a whole** (round 1, easy dataset): success at ceiling
  everywhere, but `none`/`minimal` cost 3–7 queries where `full` cost 1–2 —
  the declaration is a discovery-cost eliminator even when compensable.
- **Introspection (`intro` vs `nointro`)** changed little: `INFO` reveals value
  *lists* (via ASSERT) but never semantics or ordering roles, which is where
  the failures were.

Method notes for round 3+: success saturates fast — design tasks around
*ambiguity* (two plausible fields, misleading names, opaque codes), not lookup
difficulty; report cost (query count from the gateway log) alongside success;
`spec_round2`'s `full_plus` should become a variant using the new
`values={code: meaning}` form instead of packing the mapping into descriptions.
