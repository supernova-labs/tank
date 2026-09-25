-- Tank 0.2 — the access trail.
--
-- One `tank_access_event` per tool call, plus the rows that hang off it. The
-- normative source for this file is D2; where the other design pieces specify a
-- different shape, they cite this file rather than redefining it.
--
-- Two rules govern every line below, and they are the reason the schema looks
-- the way it does:
--
--   1. The core is guaranteed by DDL, not by the decorator's discipline. A core
--      field is non-`option`, so the server refuses an incomplete event. This
--      holds even on a SCHEMALESS table: SCHEMAFULL is what stops an extra
--      field and denounces an auto-created table, not what defends the core.
--
--   2. Absence never carries information. Every group that depends on the
--      capture tier or on policy has a sibling in `obs.*` with a closed
--      vocabulary that names the REASON. That is what replaces a NULL
--      sentinel — which is, besides, inexpressible: the Python SDK encodes
--      `None` as NONE and has no path to write NULL from a dict, so the
--      three-state encoding by sentinel could not be produced by the writer
--      even if the reader could tell them apart.
--
-- Additivity, for whoever writes 0002 (D2 §4.4):
--   A1 never remove a field, never change an existing field's type.
--   A2 a new field is born `option<>` AND with the matching `obs.*` state
--      meaning "this version did not record it".
--   A3 widening a closed vocabulary is additive; narrowing never is.
--   A4 a new value, never a new meaning for an existing one.
--   A6 a new ASSERT only lands if every existing row already satisfies it —
--      but only on a WRITABLE field. Measured: a READONLY field is skipped
--      whole on UPDATE, TYPE and ASSERT alike, so an assert added to one never
--      re-runs and is free. On a writable field it is re-evaluated on every
--      UPDATE, touched or not. In this table the writable fields are exactly
--      `error_message`, `scope_value`, `args_values` and the six `obs.*` — which
--      is to say, exactly the fields `tank prune` writes. An assert or a type
--      change on any of them breaks the prune over the whole historical series,
--      and the break only shows up on the day the prune runs.
--
--   A new `obs.<dimension>` is the expensive case: it is non-`option`, so every
--   historical row becomes un-updatable and `tank prune` breaks over the whole
--   series. The migration that adds one MUST define it with a reserved value
--   meaning "this dimension did not exist in this event" and backfill every row
--   in the same migration, before anything else writes.

-- ---------------------------------------------------------------- the ledger
--
-- The row id IS the migration number: tank_migration:1, tank_migration:2.
-- Without a version table, "this database is on 0001" and "this database has no
-- Tank tables" would be indistinguishable.

-- This file does NOT write its own row: it cannot know its own checksum. Writing
-- the ledger entry is `tank migrate`'s job, and until that command exists the
-- table stays empty — so "this database is on 0001" and "this database has no
-- Tank" are, for now, still indistinguishable. Two consequences worth knowing
-- before `tank migrate` is written, both measured: applying this file twice is a
-- clean no-op (`IF NOT EXISTS` throughout), and so is applying a MODIFIED
-- version of it — the divergence is swallowed in silence, and the checksum in
-- this ledger is the only thing that could ever detect it.
DEFINE TABLE IF NOT EXISTS tank_migration TYPE NORMAL SCHEMAFULL PERMISSIONS NONE;
DEFINE FIELD IF NOT EXISTS name         ON tank_migration TYPE string READONLY;
DEFINE FIELD IF NOT EXISTS applied_at   ON tank_migration TYPE datetime VALUE time::now() READONLY;
DEFINE FIELD IF NOT EXISTS tank_version ON tank_migration TYPE string READONLY;
DEFINE FIELD IF NOT EXISTS checksum     ON tank_migration TYPE string READONLY;

-- ------------------------------------------------- tank_access_event
--
-- Every table here carries the `tank_` prefix, matching `tank_migration`. The
-- names are ours inside the consumer's database, and an unprefixed
-- `access_event` is a name a consumer could plausibly already own — in which
-- case `DEFINE FIELD` would graft our columns onto their table without a word
-- of complaint. Renaming is free today and is a production table rename per
-- tenant after the first event.

DEFINE TABLE IF NOT EXISTS tank_access_event TYPE NORMAL SCHEMAFULL PERMISSIONS NONE;

-- ---------- time ------------------------------------------------------------
-- `ts` is the START of the call, measured by Tank. Deliberately NOT
-- `VALUE time::now()`: VALUE silently overwrites what the client sent, which
-- would turn every latency into a measurement of the write queue.
DEFINE FIELD IF NOT EXISTS ts         ON tank_access_event TYPE datetime READONLY;
-- `written_at` is the instant of the write. `written_at - ts` is the observer's
-- own cost, for free, and it is what exposes a backed-up event queue. It is
-- mandatory, not optional: it is the only way that cost is auditable from data.
DEFINE FIELD IF NOT EXISTS written_at ON tank_access_event TYPE datetime VALUE time::now() READONLY;
DEFINE FIELD IF NOT EXISTS latency    ON tank_access_event TYPE duration READONLY;

-- ---------- tenant: stamped by the server, never by the client --------------
-- With namespace-per-tenant the easiest field to corrupt is the tenant itself.
-- VALUE + READONLY makes the lie impossible: a CREATE that sends
-- ns:'other_tenant' is stored with the connection's real ns.
DEFINE FIELD IF NOT EXISTS ns ON tank_access_event TYPE string VALUE session::ns() READONLY;
DEFINE FIELD IF NOT EXISTS db ON tank_access_event TYPE string VALUE session::db() READONLY;

-- ---------- identity of the instrument (core, no backfill) ------------------
DEFINE FIELD IF NOT EXISTS tank_version     ON tank_access_event TYPE string READONLY;
-- Two fields, not one composite: with two, "same version, different hash"
-- (edited without bumping) is a GROUP BY; with a composite it is string
-- parsing in SQL. `ontology_version` is `Ontology.name@version`,
-- `ontology_hash` is `fingerprint()[:12]` — together they are `stamp()`.
DEFINE FIELD IF NOT EXISTS ontology_version ON tank_access_event TYPE string READONLY;
DEFINE FIELD IF NOT EXISTS ontology_hash    ON tank_access_event TYPE string READONLY;
-- server_version belongs in the event, not just in a report header: the SAME
-- defect changes error_class between 2.x and 3.x, so comparing error rates
-- across clients on different versions compares different things.
DEFINE FIELD IF NOT EXISTS server_version   ON tank_access_event TYPE option<string> READONLY;

-- ---------- run context: OPAQUE tokens from the caller ----------------------
-- `run_id` is TYPE string and never uuid. It is the caller's own token, and
-- uuid rejects 'conv-7d2f/msg-3' — a value from the design's own example — in a
-- core field that has no backfill.
DEFINE FIELD IF NOT EXISTS run_id          ON tank_access_event TYPE string READONLY;
DEFINE FIELD IF NOT EXISTS conversation_id ON tank_access_event TYPE option<string> READONLY;
DEFINE FIELD IF NOT EXISTS message_id      ON tank_access_event TYPE option<string> READONLY;
-- The decorator cannot originate skill_version; only the caller can. Hence
-- three states in obs.skill rather than two.
DEFINE FIELD IF NOT EXISTS skill_version   ON tank_access_event TYPE option<string> READONLY;

-- ---------- the tool --------------------------------------------------------
DEFINE FIELD IF NOT EXISTS tool_version     ON tank_access_event TYPE option<string> READONLY;
-- Derived from the DECLARED surface (name, version, scope, stage, parameters),
-- never from the body: a code hash fails in both directions — a comment-only
-- edit moves it, and moving the SQL to a module constant and changing it does
-- not. Same version with a different fingerprint in the window means someone
-- changed the contract without bumping.
DEFINE FIELD IF NOT EXISTS tool_fingerprint ON tank_access_event TYPE option<string> READONLY;
DEFINE FIELD IF NOT EXISTS stage            ON tank_access_event TYPE option<'candidate'|'evidence'> READONLY;
DEFINE FIELD IF NOT EXISTS n_refs           ON tank_access_event TYPE option<int> READONLY;
-- Reserved for a retry loop that 0.2 does not implement. Present from day one
-- because a core field cannot be added later without backfill.
DEFINE FIELD IF NOT EXISTS attempt          ON tank_access_event TYPE option<int> READONLY;

-- ---------- error: three fields, never one ----------------------------------
DEFINE FIELD IF NOT EXISTS error_type    ON tank_access_event TYPE option<string> READONLY;
DEFINE FIELD IF NOT EXISTS error_message ON tank_access_event TYPE option<string>;

-- ---------- scope -----------------------------------------------------------
DEFINE FIELD IF NOT EXISTS scope       ON tank_access_event TYPE option<string> READONLY;
DEFINE FIELD IF NOT EXISTS scope_value ON tank_access_event TYPE option<string>;

-- ---------- sampling --------------------------------------------------------
-- No DEFAULT. This was the only defaulted field in the schema, and a default
-- here asserts a positive fact: "this row stands for one call". If a future
-- sampler forgets to set it, every sampled row would silently claim weight 1
-- and every rate computed from the table would be wrong by 1/r. The writer
-- states it or the server refuses the event.
DEFINE FIELD IF NOT EXISTS sample_rate ON tank_access_event TYPE float READONLY;

-- ---------- arguments: shape always, values never by default ----------------
DEFINE FIELD IF NOT EXISTS args_shape           ON tank_access_event TYPE array<object> READONLY;
DEFINE FIELD IF NOT EXISTS args_shape[*].name   ON tank_access_event TYPE string;
DEFINE FIELD IF NOT EXISTS args_shape[*].type   ON tank_access_event TYPE string;
DEFINE FIELD IF NOT EXISTS args_values          ON tank_access_event TYPE option<array<object>>;
DEFINE FIELD IF NOT EXISTS args_values[*].name  ON tank_access_event TYPE string;
DEFINE FIELD IF NOT EXISTS args_values[*].value ON tank_access_event TYPE string;

-- ---------- obs: the event's record of its own observability ----------------
--
-- Every dimension is non-`option`, so an event missing `obs`, or missing one of
-- its keys, is refused with a message naming the field. Compare with a
-- `unobserved: array<string> DEFAULT []` design, where forgetting to populate
-- the list produces exactly the lie "everything was observed" — silently, and
-- stored. The difference between the two is the difference between a stated
-- error and a wrong number.
--
-- Each dimension that claims 'observed' carries the ASSERT that the value it
-- claims to have observed is actually there. Without it a dimension can say
-- 'observed' over an absent field, and the catalog then counts that row in the
-- denominator of "we know" — which is the one failure this schema exists to
-- prevent. Note the discovered rule: ASSERT only runs when the field HAS a
-- value, so the assert always lives on the antecedent (the present field),
-- never on the consequent.

DEFINE FIELD IF NOT EXISTS obs ON tank_access_event TYPE object;

DEFINE FIELD IF NOT EXISTS obs.scope ON tank_access_event TYPE
  'observed'|'unbound'|'undeclared'|'expired'
  ASSERT $value != 'observed' OR $this.scope_value != NONE;

-- 'expired' is here because scope_value is redactable by `tank prune`, and the
-- prune must write a state rather than an absence.
DEFINE FIELD IF NOT EXISTS obs.args ON tank_access_event TYPE
  'observed'|'shape_only'|'redacted'|'expired'
  ASSERT $value != 'observed' OR $this.args_values != NONE;

DEFINE FIELD IF NOT EXISTS obs.error_message ON tank_access_event TYPE
  'observed'|'not_applicable'|'redacted'|'expired'
  ASSERT $value != 'observed' OR $this.error_message != NONE;

DEFINE FIELD IF NOT EXISTS obs.skill ON tank_access_event TYPE
  'reported'|'none'|'not_reported'
  ASSERT $value != 'reported' OR $this.skill_version != NONE;

-- 'expired' is the amendment: refs is the dimension that feeds "units never
-- accessed", which produces a list of deletion candidates. Without it, a ref
-- expired by retention reads as a ref that never happened.
--
-- Note what this assert does NOT do. It is in-row: it holds `obs.refs` against
-- `n_refs`, which is READONLY and never goes away, NOT against the rows in
-- `tank_access_ref`. So `DELETE FROM tank_access_ref` followed by
-- `obs.refs = 'observed'` is accepted, and the same is true of `obs.plan`
-- against `tank_access_plan`. Marking those two 'expired' after a purge is a
-- convention `tank prune` has to keep; the database cannot enforce it, because
-- an ASSERT only sees `$this`.
--   observed          the call returned refs AND the declared stage stores them
--   undeclared_stage  the declared stage is `ref`, which has no rows by design;
--                     `n_refs` may still be set, and it is true, but nothing in
--                     `tank_access_ref` corresponds to it. Any question asked
--                     against that table must filter on 'observed' alone.
--   normalize_failed  the return could not be read as list[<returns>]
--   errored           the call raised before returning anything. Added because
--                     the absence had been landing as 'undeclared_stage' on
--                     events whose `stage` column was filled in on the same
--                     row — a reason that contradicted its own event.
DEFINE FIELD IF NOT EXISTS obs.refs ON tank_access_event TYPE
  'observed'|'undeclared_stage'|'normalize_failed'|'errored'|'below_mode'|'expired'
  ASSERT $value != 'observed' OR $this.n_refs != NONE;

-- The biconditional lives HERE, on the writable field, and not only on
-- `capture_mode`. An ASSERT on a READONLY field never re-runs, because nothing
-- ever writes that field again — so `tank prune`, which does
-- `UPDATE ... SET obs.plan = 'expired'`, could walk the invariant straight out
-- of the table. Stated on `obs.plan` it re-evaluates on every prune.
DEFINE FIELD IF NOT EXISTS obs.plan ON tank_access_event TYPE
  'observed'|'partial'|'unsupported_statement'|'below_mode'|'server_unsupported'|'unknown_shape'|'disabled'|'expired'
  ASSERT ($value IN ['observed','partial','expired'])
       = ($this.capture_mode IN ['gateway_plan','typed']);

-- ---------- the invariants the DATABASE enforces ----------------------------

-- A tool with no version contaminates the whole per-tool series, which is keyed
-- by (tool, tool_version).
DEFINE FIELD IF NOT EXISTS tool ON tank_access_event TYPE option<string> READONLY
  ASSERT $value = NONE OR $this.tool_version != NONE;

-- 'none' is legitimate tool-less traffic; 'stale' is an expired frame
-- (over-attribution, detected) and still names the tool. Attributing a query to
-- a tool that did not make it is worse than not attributing it.
DEFINE FIELD IF NOT EXISTS attribution ON tank_access_event TYPE 'in_frame'|'stale'|'none' READONLY
  ASSERT $value = 'none' OR $this.tool != NONE;

-- Declared when the gateway is built, never inferred by heuristic.
DEFINE FIELD IF NOT EXISTS caller_kind ON tank_access_event TYPE
  'tool'|'migration'|'maintenance'|'console'|'eval'|'unknown' READONLY;

-- error_class is closed and sustains blame attribution; error_type carries the
-- raw FQN and is how a missing class is discovered without a migration. 'none'
-- is a value, not an absence, so count(error_class != 'none') is safe.
DEFINE FIELD IF NOT EXISTS error_class ON tank_access_event TYPE
  'none'|'timeout'|'cancelled'|'connection'|'auth'|'query_syntax'|'not_found'|'permission'|'server'|'tool' READONLY
  ASSERT $value = 'none' OR $this.error_type != NONE;

-- The mode declares what HAPPENED, never what the configuration intended. The
-- biconditional is stated on both sides on purpose: this one catches a bad
-- event at CREATE, the one on obs.plan catches a bad UPDATE.
DEFINE FIELD IF NOT EXISTS capture_mode ON tank_access_event TYPE
  'direct'|'gateway'|'gateway_plan'|'typed' READONLY
  ASSERT ($value IN ['gateway_plan','typed'])
       = ($this.obs.plan IN ['observed','partial','expired']);

DEFINE INDEX IF NOT EXISTS idx_ae_ts      ON tank_access_event FIELDS ts;
DEFINE INDEX IF NOT EXISTS idx_ae_tool_ts ON tank_access_event FIELDS tool, ts;
DEFINE INDEX IF NOT EXISTS idx_ae_mode_ts ON tank_access_event FIELDS capture_mode, ts;
DEFINE INDEX IF NOT EXISTS idx_ae_err_ts  ON tank_access_event FIELDS error_class, ts;
DEFINE INDEX IF NOT EXISTS idx_ae_run     ON tank_access_event FIELDS run_id;

-- -------------------------------------------------- tank_access_plan
--
-- A separate table rather than an object nested in the event. D3 specifies the
-- plan embedded, with `elided` as a boolean; this file is normative and D3
-- cites it. Three reasons: pruning plans is a DELETE over a ts range rather
-- than an UPDATE rewriting the whole event row in an MVCC store; denormalized
-- ts/tool let all tier-3a analytics run over one table with no join; and the
-- row id is the event's own id, so "the plan for this call" is a record-id
-- lookup with no index at all.

DEFINE TABLE IF NOT EXISTS tank_access_plan TYPE NORMAL SCHEMAFULL PERMISSIONS NONE;
DEFINE FIELD IF NOT EXISTS event ON tank_access_plan TYPE record<tank_access_event> READONLY;
DEFINE FIELD IF NOT EXISTS ts    ON tank_access_plan TYPE datetime READONLY;
DEFINE FIELD IF NOT EXISTS tool  ON tank_access_plan TYPE option<string> READONLY;

-- The three below are un-backfillable by nature: without them an old row is
-- unreadable once the adapter changes.
DEFINE FIELD IF NOT EXISTS schema_version   ON tank_access_plan TYPE int READONLY;
DEFINE FIELD IF NOT EXISTS source           ON tank_access_plan TYPE 'explain'|'typed' READONLY;
DEFINE FIELD IF NOT EXISTS server_major     ON tank_access_plan TYPE int READONLY;
-- Hash of the SQL with literals ALREADY REDACTED: groups "the same query"
-- without storing its text. The raw SQL never touches disk.
DEFINE FIELD IF NOT EXISTS query_shape_hash ON tank_access_plan TYPE option<string> READONLY;

DEFINE FIELD IF NOT EXISTS tables    ON tank_access_plan TYPE array<string> READONLY;
DEFINE FIELD IF NOT EXISTS indexes   ON tank_access_plan TYPE array<string> READONLY;
-- Closed and ours. SurrealDB's own operator names stay out, in unknown_ops,
-- which is what lets the adapter evolve without a migration.
DEFINE FIELD IF NOT EXISTS ops       ON tank_access_plan TYPE
  array<'scan'|'index'|'fulltext'|'knn'|'record_id'|'count'|'graph'|'unknown'> READONLY;
DEFINE FIELD IF NOT EXISTS row_limit ON tank_access_plan TYPE option<int> READONLY;

DEFINE FIELD IF NOT EXISTS attrs          ON tank_access_plan TYPE array<object> READONLY;
DEFINE FIELD IF NOT EXISTS attrs[*].table ON tank_access_plan TYPE option<string>;
DEFINE FIELD IF NOT EXISTS attrs[*].attr  ON tank_access_plan TYPE string;
DEFINE FIELD IF NOT EXISTS attrs[*].role  ON tank_access_plan TYPE
  'filter'|'sort'|'projection'|'group'|'traversal';
-- The "tab.attr" projection of the list above: "which declared attrs were never
-- touched" resolves to one GROUP BY over this plus a set difference in Python,
-- instead of array::distinct over everything in memory.
DEFINE FIELD IF NOT EXISTS attrs_flat ON tank_access_plan TYPE array<string> READONLY;

-- Only what matched a declared Attr.values. A value that is not in a declared
-- closed vocabulary is structurally unstorable, which is where the PII defence
-- and the analytics capability come from — the same rule, not a trade-off.
DEFINE FIELD IF NOT EXISTS matched_values          ON tank_access_plan TYPE array<object> READONLY;
DEFINE FIELD IF NOT EXISTS matched_values[*].attr  ON tank_access_plan TYPE string;
DEFINE FIELD IF NOT EXISTS matched_values[*].op    ON tank_access_plan TYPE string;
DEFINE FIELD IF NOT EXISTS matched_values[*].value ON tank_access_plan TYPE string;

DEFINE FIELD IF NOT EXISTS sort           ON tank_access_plan TYPE array<object> READONLY;
DEFINE FIELD IF NOT EXISTS sort[*].attr   ON tank_access_plan TYPE string;
DEFINE FIELD IF NOT EXISTS sort[*].dir    ON tank_access_plan TYPE 'asc'|'desc';
DEFINE FIELD IF NOT EXISTS sort[*].source ON tank_access_plan TYPE 'observed'|'from_index';

-- The most important field in the table: it is what stops "did not filter by X"
-- being read where the truth is "the filter was inside a function and the
-- database printed (...)". Without it, tier 3a lies with confidence.
DEFINE FIELD IF NOT EXISTS elided      ON tank_access_plan TYPE
  array<'filter'|'sort'|'projection'|'group'|'subquery'|'function_arg'> READONLY;
DEFINE FIELD IF NOT EXISTS unknown_ops ON tank_access_plan TYPE array<string> READONLY;

DEFINE INDEX IF NOT EXISTS idx_ap_ts      ON tank_access_plan FIELDS ts;
DEFINE INDEX IF NOT EXISTS idx_ap_tool_ts ON tank_access_plan FIELDS tool, ts;

-- --------------------------------------------------- tank_access_ref
--
-- NEVER a graph edge. An edge is deleted in cascade when either endpoint goes
-- away, so the day a consumer deletes a document would also delete the proof
-- that it was delivered, rewriting the usage metric retroactively.

DEFINE TABLE IF NOT EXISTS tank_access_ref TYPE NORMAL SCHEMAFULL PERMISSIONS NONE;
DEFINE FIELD IF NOT EXISTS event ON tank_access_ref TYPE record<tank_access_event> READONLY;
-- ts and tool denormalized: the purge has to be a DELETE over a range on this
-- table's own index. Purging across the link would be a table scan.
DEFINE FIELD IF NOT EXISTS ts    ON tank_access_ref TYPE datetime READONLY;
DEFINE FIELD IF NOT EXISTS tool  ON tank_access_ref TYPE option<string> READONLY;

-- The subject is the DECLARED TYPE, not the table. That is what lets the schema
-- survive a materialized index projection: the table changes, the type does not.
DEFINE FIELD IF NOT EXISTS unit_type ON tank_access_ref TYPE string READONLY;
-- `record` with no parameter: accepts any of the consumer's tables, so the
-- framework's DDL never enumerates their domain.
DEFINE FIELD IF NOT EXISTS unit      ON tank_access_ref TYPE option<record> READONLY;
-- Non-`option`, written ALWAYS — including when `unit` is present, where it
-- holds <string> of the record id. D1 said "always" and D2 said `option`; this
-- resolves it toward always, and that choice is what keeps the decision of
-- WHERE the trail lives reversible. A dangling `unit` link is unreadable once
-- the target is gone, while `unit_key` still identifies what was delivered.
-- Measured cost: 414ms against 439ms for 20k inserts, and ~15 B/row.
DEFINE FIELD IF NOT EXISTS unit_key  ON tank_access_ref TYPE string READONLY;

-- Both `option<string>` and both present from the first migration. The third
-- option — the boundary API accepting them while nothing persists them — is the
-- one that cannot stand: `tank_access_ref` is purged on a short horizon, so by
-- the time 0.3 needs `evidence_link` there would be no history left to backfill.
-- What Tank does NOT do is verify them; see the NOT_VERIFIED list.
DEFINE FIELD IF NOT EXISTS unit_version ON tank_access_ref TYPE option<string> READONLY;
DEFINE FIELD IF NOT EXISTS content_hash ON tank_access_ref TYPE option<string> READONLY;

-- `stage` and `rank` are born with the first event because they are impossible
-- to reconstruct afterwards.
DEFINE FIELD IF NOT EXISTS stage ON tank_access_ref TYPE 'candidate'|'evidence' READONLY;
DEFINE FIELD IF NOT EXISTS rank  ON tank_access_ref TYPE option<int> READONLY;
DEFINE FIELD IF NOT EXISTS score ON tank_access_ref TYPE option<float> READONLY;

DEFINE INDEX IF NOT EXISTS idx_ar_ts       ON tank_access_ref FIELDS ts;
DEFINE INDEX IF NOT EXISTS idx_ar_event    ON tank_access_ref FIELDS event;
DEFINE INDEX IF NOT EXISTS idx_ar_unit     ON tank_access_ref FIELDS unit;
DEFINE INDEX IF NOT EXISTS idx_ar_type_ts  ON tank_access_ref FIELDS unit_type, ts;
DEFINE INDEX IF NOT EXISTS idx_ar_key_ts   ON tank_access_ref FIELDS unit_key, ts;

-- ------------------------------------------------ tank_access_rollup
--
-- NOT `DEFINE TABLE ... AS SELECT`. A precomputed view DECREMENTS when its
-- source rows are deleted, so a rollup in a view rewrites usage history the
-- moment `tank prune` runs. This is a plain append-only table, written BEFORE
-- the DELETE.

DEFINE TABLE IF NOT EXISTS tank_access_rollup TYPE NORMAL SCHEMAFULL PERMISSIONS NONE;
-- Deterministic id from the slice keys:
-- tank_access_rollup:['2026-09-22','search','gateway_plan']
DEFINE FIELD IF NOT EXISTS day          ON tank_access_rollup TYPE datetime READONLY;
DEFINE FIELD IF NOT EXISTS tool         ON tank_access_rollup TYPE option<string> READONLY;
DEFINE FIELD IF NOT EXISTS capture_mode ON tank_access_rollup TYPE string READONLY;
DEFINE FIELD IF NOT EXISTS calls        ON tank_access_rollup TYPE int;
DEFINE FIELD IF NOT EXISTS errors           ON tank_access_rollup TYPE array<object>;
DEFINE FIELD IF NOT EXISTS errors[*].class  ON tank_access_rollup TYPE string;
DEFINE FIELD IF NOT EXISTS errors[*].n      ON tank_access_rollup TYPE int;
-- p50/p95 of the bucket. NEVER re-aggregate a percentile across buckets.
DEFINE FIELD IF NOT EXISTS p50_ms  ON tank_access_rollup TYPE option<float>;
DEFINE FIELD IF NOT EXISTS p95_ms  ON tank_access_rollup TYPE option<float>;
DEFINE FIELD IF NOT EXISTS n_refs  ON tank_access_rollup TYPE option<int>;
-- The per-obs-state counts: the day's denominator, frozen before the purge.
-- Without it, "among those that could have seen this" dies with the rows.
DEFINE FIELD IF NOT EXISTS obs_counts        ON tank_access_rollup TYPE array<object>;
DEFINE FIELD IF NOT EXISTS obs_counts[*].key ON tank_access_rollup TYPE string;
DEFINE FIELD IF NOT EXISTS obs_counts[*].n   ON tank_access_rollup TYPE int;
DEFINE FIELD IF NOT EXISTS source_rows   ON tank_access_rollup TYPE int;
DEFINE FIELD IF NOT EXISTS window_closed ON tank_access_rollup TYPE bool;
DEFINE FIELD IF NOT EXISTS tank_version  ON tank_access_rollup TYPE string;
DEFINE INDEX IF NOT EXISTS idx_rl_day ON tank_access_rollup FIELDS day;
