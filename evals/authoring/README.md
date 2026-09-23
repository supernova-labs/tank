# Authoring eval — declarative API vs typed classes

Tests the premise of the `spike/typed-declaration` branch: that consumers
(in practice, often coding agents) declare ontologies with fewer errors and
fewer iterations using typed classes than with the declarative objects.

The retrieval-side ablation harness (`evals/ablation/`) cannot measure this —
both forms derive an identical IR by construction. So this harness flips the
direction: agents *write* declarations from a prescriptive spec, and the judge
diffs the IR their file derives against a gold IR (`model_dump`, normalized so
declaration order never counts). The spike's own equivalence guarantee is the
measuring instrument.

## Pieces

- `specs.py` — 4 prescriptive briefs (single type; chunks+locator+field_link;
  the full surface with vector/fulltext/freshness/scope; extending an existing
  declaration). Prescriptive so the gold is unique and the eval measures API
  ergonomics, not domain judgement.
- `golds/task*.py` — gold IRs in declarative form; `golds/typed_refs/` are my
  typed translations, used only to verify both forms reach the same IR (they
  do, all 4 tasks).
- `starters/` — task 4's existing declaration, one per arm.
- `judge.py` — loads a submission, derives its IR, diffs against gold, logs
  every attempt (max 6 per run); enforces the arm (typed must subclass
  Unit/Edge, declarative must not). Run it from the spike worktree so its
  `tank` is importable.
- `gen_runs.py` / `score.py` — same pattern as evals/ablation.

## Findings (round 1, 2026-09-18, 40 Sonnet agents, k=5, spike @1693b04)

- **Final success saturated: 40/40 in both arms, ≤2 submissions each.** With a
  validator loop in place, both APIs converge fast — the iteration loop, not
  the API form, is what guarantees correctness.
- **First-try exactness split: declarative 15/20, typed 6/20.** Every single
  first-try failure in the whole round — both arms — was the SAME error:
  declaring full-text search on the text field when the brief said only
  "searchable text lives in field X". No other error class occurred.
- **The asymmetry is the API finding**: with identical brief wording, typed
  agents over-declared far more (T1: 0/5 vs 5/5 first-try) — the marker
  literally named `Searchable` sits next to `Text()` and pattern-matches the
  word "searchable" in prose. Naming steers authors; `Searchable` invites
  over-declaration. Worth renaming (e.g. `FullTextIndex`) or documenting hard.
- **The feared metaprogramming traps did not bite.** T3 — the hardest task,
  including `Annotated[Embedding[8], Embed(...)] | None` (the union trap the
  spike doc warns about) — was 5/5 first-try exact in BOTH arms. Zero
  construction failures, zero arm violations anywhere.
- **Caveat**: the dominant error is confounded with the brief's wording
  ("searchable text" was my ambiguity, and real-world specs are ambiguous —
  that interaction is itself the finding). A round 2 with unambiguous wording
  would measure the residual gap; k=5, one model, one spec style.

Verdict for D4/issue #3: the eval does not refute the spike — typed is as
convergent as declarative and its complexity didn't hurt — but it removes one
argument (agents don't need classes to get it right) and adds one requirement
(marker names are UX surface; `Searchable` misleads).

## Findings (round 2, 2026-09-18, 80 agents: 40 Sonnet + 40 Haiku, k=5)

Same tasks, prompts and budget; the model became a dimension.

- **Final success stayed saturated: 80/80, worst case 4 submissions.** The
  validator loop rescues even the small model — Haiku never ran out of budget.
- **First-try exact:** declarative/Sonnet 14/20 (replicates round 1's 15/20),
  typed/Sonnet 6/20 (replicates exactly), declarative/Haiku 6/20, typed/Haiku
  4/20. Typed ≤ declarative at both capability levels.
- **The `Searchable` trap is model-independent:** 42 of the 50 failing first
  tries were, again, ONLY the spurious fulltext — across both models and arms.
  Confirmed as an API/wording interaction, not a capability artifact.
- **New typed-only failure mode, Haiku-only: implicit naming.** 4 runs named
  the class `FAQ`; `_snake` derives the unit name `f_a_q` (spec: `faq`) — the
  agents didn't notice until the judge diffed it. The declarative form is
  immune (the name is explicit). Acronym class names are common; the typed
  layer needs an explicit `name=` escape or smarter acronym snake-casing,
  and the docs must warn.
- **Haiku's other slips** (declarative too): 3 runs forgot the `text` mapping,
  1 invented a freshness rule. Small-model noise, not arm-specific.
- **T3 — the hardest, most explicit spec — stayed ~perfect for everyone**
  (19/20 first-try across the four groups): ambiguity, not complexity, is
  what produces errors, at every capability level.

## Findings (round 3, 2026-09-18, 80 agents, unambiguous wording — the control)

`specs_v2.py`: identical briefs except the one ambiguous phrase ("searchable
text lives in field X") replaced by an explicit text-mapping sentence + a
closing "no indexes unless specified" rule. Everything else unchanged, so
round 3 vs round 2 isolates the ambiguity effect. Predictions were registered
before running; all three held:

- **The fulltext error collapsed to ZERO** (was 42 of 50 first-try failures).
  The ambiguity×naming thesis is proven, not inferred.
- **Three of the four groups became perfect at first try (20/20)** — including
  declarative/Haiku, which had been 6/20. With clear specs, the declarative
  form was error-free even on the small model.
- **The entire residual gap is typed×Haiku (14/20)**, and it is all the
  implicit-naming family, which survived exactly as predicted: `FAQ` →
  `f_a_q` in 4 of 5 T4 runs; one run's class-name typo (`CovesManual`)
  silently propagated into the relation name; plus one loud construction
  error and one edge-vs-field_link misuse (both recovered in 1 iteration).
## Findings (round 4, 2026-09-18) — do AI-written specs induce errors?

`gen_specwriting.py`: writer agents see the gold IR and write a brief for a
colleague; implementer agents see ONLY the brief and get ONE submission, no
judge loop. 18 briefs (3 tasks × free-prose / structured-template × 3 writers)
→ 36 implementations, then re-run with a neutral implementer prompt (the first
pass carried an anti-over-declaration rule — my own confound) → 36 more.

- **Induction rate: 0 of 72 implementations diverged.** Both prose styles, both
  arms, both implementer promptings. The prediction going in was "high"; the
  measurement says the opposite in this condition.
- **Why**: writers transcribing a known declaration speak in Tank's terms.
  4 of 6 free-prose briefs for index-free types volunteered "no vector index,
  no fulltext index" unprompted; 6 of 6 template briefs did (the slot forces
  it). The 2 silent briefs still induced nothing — they anchored the text
  mapping on "the type's main text content" rather than on "searchable".
- **The template could not be shown to help** because free prose was already at
  ceiling. It did raise explicit index negation from 4/6 to 6/6, so it remains
  cheap insurance, not a proven fix.
- **What this does NOT measure**: a spec written from *business intent*, with
  no target declaration in hand, by a writer not told they are the only source
  of truth. That is the condition that produced the round-1/2 ambiguity (I
  wrote those briefs). The risk lives there, not in transcription.

- **Bottom line for D4**: with unambiguous specs the two forms tie at Sonnet
  level; the typed form's remaining measured cost is implicit naming on small
  models — concrete, fixable asks for the spike (explicit `name=` on classes,
  acronym-aware snake-casing, rename `Searchable`). After those, the eval
  finds no correctness reason to prefer either form; the choice is human
  ergonomics and domain-model integration.

## Running

```bash
git worktree add ../tank-spike origin/spike/typed-declaration && (cd ../tank-spike && touch .env && uv sync)
uv run python evals/authoring/gen_runs.py --round round1 --reps 5
# run one agent per manifest entry; collect structured outputs into results/round1_raw.json
uv run python evals/authoring/score.py --round round1 --raw evals/authoring/results/round1_raw.json
```
