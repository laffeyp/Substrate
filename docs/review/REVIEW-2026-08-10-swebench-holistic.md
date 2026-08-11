# REVIEW — SWE-bench work holistically, against Substrate and against SDD (2026-08-10)

*Companion to
`docs/review/REVIEW-2026-08-10-swebench-confirmatory-revert-v2.md` (which reads v2
of the design) and
`docs/review/REVIEW-2026-08-09-sdd-conformance-swebench-additions.md` (which reads
SDD adherence up to Aug 9). This review looks across the whole SWE-bench effort
and asks four questions: is Substrate being used, where are we rebuilding what
Substrate already ships, does the shape hold together as one idea, and does the
work fit the North Star at
`docs/NORTH-STAR-2026-08-10-v5.md` — an assay any topology of the right shape can
plug into.*

*Sources read: the design chain (v1, v2, v3 at 424 lines), the
postmortem, the north star v5, the SDD conformance review (2026-08-09), the
walltime review (2026-08-09), the SWE-bench first-principles doc (2026-08-09),
the solver design v1, the close-the-loop roadmap round 3 (203 lines), the
assay roadmap, the tail of `process/BLACKBOARD.md`, and the code:
`api.py`, `assay/suite.py`, `assay/oracle.py`, `assay/run.py`,
`assay/swebench_suite.py`, `assay/swebench_matrix.py`, `assay/swebench.py`,
`topologies/swebench_solver/` (14 files, 3593 lines),
`scripts/assay_swebench_confirmatory.py` (837 lines),
`kernel/composition.py:embedded_substrate`, `sdd-kit-2/AGENTS.md`.*

---

## Verdict

The core of the work is right. `swebench_repair_topology` is a real Substrate
topology using typed events, producers, views, triggers, a watchdog, and the
`SelectedPatch` output the assay grader consumes. The assay Suite/Arm/Case
scaffolding sits on `assay/suite.py`'s generic primitives. The bridge to the
external `swebench` package is documented at
`docs/swebench-bridge-mapping.md` with a runtime `verify_constants` check. The
Oracle taxonomy is honored — SWE-bench grades run through `ExternalGraderOracle`
with `replayable=False`. The v3 design routes vocabulary changes through the
proper SDD halts. Pre-registration exists and gates the runner. The firewall is
structural.

The work under-uses Substrate in three places, reinvents pieces of the assay
harness in one, drifts from the North Star's topology-agnostic assay in one,
and drags a dead heavy topology through the codebase for reasons no one has
written down. SDD adherence is roughly 85 percent (the conformance review's own
number, still fair) with the same seven gaps still open plus two new ones this
review adds. The idea flow reads coherent from postmortem through v3; the
older layers (`swebench_solver_topology`, `SwebenchExtractOnlyOracle`, the batch
grade) sit alongside the new shape without a plan to retire them.

Nine concrete moves close the gap, ranked at the end.

---

## What Substrate ships, and what the SWE-bench work uses of it

Read `src/substrate/api.py` for the public surface. Fifty-plus primitives:
`Producer`, `ProducerFactory`, `Responder`, `View`, `TriggerContext`;
`BufferView`, `KindBuffer`, `KindCount`, `PerKindLatest`,
`StartedCompletedCounts`; `Once`, `PerEvent`, `PerKey`, `WhileTrue`, `Logical`,
`WallClock`; `threshold_count`, `all_completed`, `quiescence_with_watchdog`,
`pause_await_input`, `cancel_all_others`, `any_of`, `all_of`;
`TopologyBuilder`, `register_topology`, `Runtime`; `read_record`, `content_hash`,
`canonical_bytes`; `attach`, `LiveRecord`; `embedded_substrate`; `replay`,
`assert_replayable`; `explain_producer`, `trace_ancestry`, `view_at`,
`first_divergence`; `narrate`, `run_graph`, `topology_graph`; the typed exception
hierarchy; `run_conformance`.

The SWE-bench work uses: `TopologyBuilder`, `Runtime`, all view kinds,
`quiescence_with_watchdog`, `any_of`, `threshold_count`, `SelectedPatch` as
typed event, `Result` (now with `Verdict`), `ExternalGraderOracle`,
`register_topology` (indirectly via `bundled.py`), `read_record`,
`assert_replayable` at boundary tests, `narrate` in `assay/run.py:project_reproduction_for_selected`,
and the whole assay `Suite/Arm/Case` shape.

The SWE-bench work does not use: `embedded_substrate` (the nested-topology
composition that the round-3 solver design at
`docs/swebench-solver-design.md:82-86` explicitly said would factor the "best-of-N
plus correction loop" once for three consumers, `coding_flow`, `swebench_solver`,
and `code_evolution`); `attach`/`LiveRecord` for observing a running run;
`explain_producer` or `first_divergence` for post-run debugging; `run_graph` /
`topology_graph` (the substrate-ui already renders these but nothing in the
confirmatory shows the SWE-bench topology as a graph); `run_suite` (the assay
control-plane's outer walker, `assay/run.py:101`); the typed exception hierarchy
at the runner (which reinvents `_classify_cell_error` at
`scripts/assay_swebench_confirmatory.py:146`).

The gap between what ships and what is used is where the wheel-reinvention lives.

---

## Where the work reinvents what Substrate ships

### 1. `assay_swebench_confirmatory.py` bypasses `run_suite`

`assay/run.py:77-112` defines `run_arm_on_case(arm, case, oracle, root)` and
`run_suite(suite, roots)` — the outer walker that runs each `(arm, case, trial)`
at a minted root, times it with `time.monotonic()`, sums `ModelUsage` off the
record into `UsageTotals`, grades with the Oracle, and returns `CaseResult`s.
This is the generic assay control plane.

`scripts/assay_swebench_confirmatory.py` is 837 lines and does its own version
of most of this. It reimplements the outer loop with `asyncio.Semaphore`,
per-cell `asyncio.wait_for`, salvage-mode regrade, checkpointed resume,
cell-row writing, the typed error taxonomy, batch grade dispatch, and the
report projection. Bench_coding.py (the coding assay's confirmatory) exists as
the pattern, and the round-3 roadmap sprint 144a is a punch list of "parity
gaps against bench_coding.py."

The result is two runners with divergent shapes: the generic `run_suite` used
by every other assay, and a bespoke 837-line SWE-bench runner. Sprint 144a
closes the gaps against bench_coding.py, not against `run_suite`. The two are
converging by hand rather than through Substrate.

The right move is to identify what the SWE-bench runner actually needs
that `run_suite` lacks — salvage, resume, per-cell wall budget, typed cell
rows, batch grade — and either extend `run_suite` to carry those (they are
generic assay concerns, not SWE-bench-specific), or factor them into
`assay/run.py` helpers the runner calls. Under either shape, the 837 lines
should be closer to 200. The 600 that fall out are Substrate concerns pretending
to be SWE-bench concerns.

### 2. The five matrix arms wrap one topology at different (n, max_rounds)

`assay/swebench_matrix.py:154-303` defines five arm factories:
`single_draft_baseline_arm`, `n_drafts_no_correction_arm`,
`n_drafts_repair_ensemble_arm`, `baseline_matched_compute_arm`, `repair_arm`.
Each is 15-30 lines. Each calls `_build_solver_arm_from_payload` at line 90
with different values for `n`, `max_rounds`, and the responder list.

Substrate provides `Arm` at `assay/suite.py:63` as a data class taking
`name`, `role`, and `build(case) -> Topology`. Five arms differing only in two
integers and a list is one arm factory taking those as parameters, not five.
`Arm` supports this shape directly.

The five separate factories exist because the sprint history built them one
by one. They read as five decisions when they are one parameter table. This
matters because a new arm — say, a `tool_loop`-based arm — needs a new
factory in a file dedicated to variants of the same topology, which is exactly
the wrong signal for "any topology of the right shape is a valid arm" (the
North Star's assay-roadmap claim at `docs/swebench-assay-roadmap.md:28-32`).

The right move: one `swebench_repair_arm(name, role, *, models, n, max_rounds)`
factory, plus a data table naming the five current arms. Every future SWE-bench
arm that fits the repair topology adds a row. Every future arm that fits a
different topology (tool_loop, best_of_n, code_evolution) gets its own arm
factory. The matrix reads as data.

### 3. The heavy topology duplicates the swebench harness

`topologies/swebench_solver/select_exec.py:80-100` and
`topologies/swebench_solver/select_docker.py:153-192` implement
`_select_exec_factory`, which fires `docker run --rm` per applied candidate
patch to execute pytest inside the instance's evaluation image, then reranks
the candidates by test outcomes. `swebench.py:242-288` calls the same swebench
harness for grading. Both apply the patch, both spin the eval image, both run
pytest, both parse test outcomes. The postmortem's RC1 already names this: the
topology grew a duplicate of the grader.

`_first_patch_selector_factory` at `assemble.py:198` — the June 27 selector
that picks the first candidate whose validator returned `passed=True` — needs
no in-topology test execution. It reads `Verdict` events off the bus and picks
the first PASS. That is Substrate primitives, straight.

The v3 design keeps the heavy topology "for research use," renamed to
`swebench_solver_topology_with_test_selection`. No sprint plans a study that
measures the value of in-topology test-based selection versus harness-only
selection. That study is the only justification for keeping the heavy
topology alive; without it, `select_exec`, `select_docker`, `select_regression`,
`repro_base_validate`, `reproduction` — five files totaling roughly 750 lines
under `topologies/swebench_solver/` — are dead code awaiting a caller that
never comes. Postmortem RC1 will return through them the moment a
well-intentioned refactor pipes them back through a matrix arm.

The right move: either commit to a specific study of in-topology selection with
a sprint that runs it against `swebench_repair_topology` on the same cases and
reports the delta, or delete the heavy topology (adjusted for SDD hard rule 12
— move it into a `_deprecated/` folder with a KIT_DIARY entry naming the last
sha it was called from and the reason for retirement). Alive-for-research
without a research plan is engineering waste dressed as optionality.

### 4. Custom exception taxonomy in the runner

`scripts/assay_swebench_confirmatory.py:141-183` defines `_ERROR_CELL_TIMEOUT`,
`_ERROR_DOCKER`, `_ERROR_GIT`, `_ERROR_UNCLASSIFIED`, and
`_classify_cell_error(exc)`. Substrate exports a typed exception hierarchy at
`src/substrate/errors.py` re-exported through `api.py`:
`SubstrateError`, `BusLockedError`, `RegistrationError`,
`UnsupportedPlatformError`, `FsyncError`, `ProducerNotFound`,
`SequenceOutOfRange`, `InputTypeError`, `ReplayError`, `RecordIncompleteError`,
`RecordGapError`. The runner's taxonomy overlaps zero of these — Substrate's
errors are about the record and the runtime; the runner's are about Docker,
Git, and the SWE-bench harness.

This is legitimate reinvention (Substrate has no Docker or Git errors), but
the runner's four strings sit alone. There is no `SwebenchHarnessError`
class hierarchy that the runner catches by type; the runner does
`if "docker" in msg or "container" in msg` at line 179 to identify a Docker
error. String-matching an exception's `repr()` is exactly the drift pattern
Substrate's own exception hierarchy exists to eliminate — see the api.py
docstring at line 3-17 ("handles errors BY TYPE, not by string-matching class
names").

The right move: `assay/swebench_errors.py` (new, ~40 lines) with typed
exceptions — `DockerDaemonError`, `ContainerCrashed`, `GitApplyFailed`,
`HarnessTimeout`, `HarnessImageMissing`. The runner catches by type. The
grader raises typed. The oracle maps typed exception → `Verdict.NO_VERDICT`
with the appropriate reason string from the shared `_HARNESS_REASONS` closed
set the v3 design specifies. One lexicon, one taxonomy, one place.

---

## Where the flow of ideas breaks coherence

### 5. `swebench_repair_topology` and `swebench_solver_topology` are two topologies where one would do

Both live at `topologies/swebench_solver/assemble.py`, both take a
`PreparedPayload`-shaped input, both emit `SelectedPatch`. The heavy one adds
`repro_gen`, `repro_base_validate`, `select_exec`, `selector`, plus the
in-topology Docker runner. The light one has three stages.

A Substrate-shaped fix: one topology with a boolean or optional-producer kwarg
that turns test-based selection on or off, so the two shapes are ONE topology
with ONE registration and one place to change. Currently the arm helper picks
between two topologies at build time, and every consumer of the topology has
to know which one it wants. The v3 design's rename (`_with_test_selection`)
still leaves two topologies; the underlying redundancy is not fixed.

This matters for the North Star's "named strategies" pattern
(`NORTH-STAR-2026-08-10-v5.md` T3): a strategy `swebench.repair` is one name;
`swebench.repair_with_test_selection` is a second name for a variant that
should be a parameter. Two topologies means two strategy names means two
mental models.

### 6. Two grading paths, two oracle classes

`SwebenchRecordOracle` at `swebench.py:380` grades inline: the grader function
does one Docker harness call per cell during the sweep. `SwebenchExtractOnlyOracle`
at `swebench.py:515` grades in two phases: during the sweep it returns
`passed=False` with `detail="deferred: patch=<len>"`, and `batch_grade_from_records`
at line 587 runs one big harness call over every recorded patch after the
sweep finishes.

The v3 design at line 168 says the extract-only oracle "stays in the codebase for
the day someone wants a two-phase runner with an in-topology selector." Same
pattern as finding 3: kept alive without a use case. Meanwhile
`SwebenchExtractOnlyOracle.grade` returns `passed=False` unconditionally during
the sweep — meaning the record temporarily carries a lie until batch grade
overwrites it. The lie is honest (the `detail` says "deferred"), but a record
that carries known-false values is a record that violates the vocabulary
contract.

The right move: pick one path. Inline is the June 27 shape and the v3 design's
default. Batch was added in commit `7e34feb` to fight the heavy topology's
Docker load. Once the light topology is the only topology dispatched, batch's
justification evaporates. Delete `SwebenchExtractOnlyOracle` and
`batch_grade_from_records` in the same commit that flips
`SWEBENCH_BATCH_GRADE` to `"0"`.

### 7. Three separate timeout regimes

Topology watchdog: `swebench_repair_topology(watchdog_seconds: float = 60.0)`
at `assemble.py:266`, overridden by the v3 arm helper to 900s.

Runner per-cell timeout: `RUN_TIMEOUT = float(os.environ.get("SWEBENCH_RUN_TIMEOUT", "1800"))`
at `scripts/assay_swebench_confirmatory.py:207`.

Grader per-instance timeout: read from `assay/swebench_timeouts.json` per repo,
10 to 90 minutes.

Three timeouts, three lexicons, three defaults. The runner's `RUN_TIMEOUT` is
static across every cell; the grader's is per-repo; the topology's is a
watchdog on quiescence, not on wall. A cell that runs 30 min in the topology,
20 min in Docker, and 5 min in git operations blows through the RUN_TIMEOUT
before the grader even fires. The v3 design's per-cell budget calculation
(topology watchdog + grade timeout + 5-min margin) sums them but does not
unify them.

The right move: one budget policy, computed per cell from the per-repo grade
timeout table, applied at one enforcement point (the runner's per-cell
`asyncio.wait_for`), with the topology's watchdog and the grader's timeout
both derived from it. One number per cell, visible in the cell row, checkable
against the budget.

### 8. The North Star claim of topology-agnostic assay is not being executed

`docs/swebench-assay-roadmap.md:5-8` says the goal is "make SWE-bench a
benchmark that any substrate orchestration of the right shape can be run
against and measured — the same way `coding.py` already does for a firewalled
coding benchmark. Not one bespoke solver."

The current five arms all wrap `swebench_repair_topology` at different
(n, max_rounds). None is a structurally different topology. `topologies/tool_loop/`,
`topologies/best_of_n/`, `topologies/code_evolution/`, `topologies/pair_coding/`
all exist. None appears as a SWE-bench arm. The mechanism claim the North
Star's T5 rides on — small-model orchestration beats single-model — cannot be
made against a comparator that runs the same topology at lower N. That measures
compute, not mechanism.

A meaningful matrix has structurally distinct topologies. A `tool_loop` arm
(one model with read/edit/bash tools on the checkout) would be the closest
analog to the SWE-agent shape everyone in the field cites. A `best_of_n` arm
would be pure sampling, no repair. `code_evolution` would be EA-style mutation.
The current five arms answer "does more N help repair" (a small question); a
mixed matrix answers "which topology shape produces better SWE-bench patches
at matched compute" (the actual North Star question).

This is the largest gap in the whole effort. The assay pattern is right, the
Substrate primitives are right, the Adapter is right; nothing dispatches a
second topology shape at SWE-bench.

### 9. The vocabulary was designed sprint-by-sprint, not at Sprint 0

Copied from the SDD conformance review's Gap 1 (still open). The
`swebench_solver` sub-topology's tags grew sprint by sprint from 133 onward:
`SuspectFiles`, `SuspectElements`, `EditLocations`, `ReproductionTest`,
`TestResults`, `AppliedPatch`, `SelectedPatch`, `RepairSummary`, `Reproduction`,
`Solved`, `Draft`, `Candidate`, `Exhausted`. Three vocab halts landed in
sprints 147-149 after the 108/291 exploratory run had already reported a
number. `AGENTS.md` hard rule 12 cites this as soundfield's failure mode
(vocabulary materialized at sprint 60 of 67). The remedy — a Sprint 0
vocabulary session for the SWE-bench sub-topology, retrofit as `signals/0.2.json`
— was proposed in the conformance review and never landed.

---

## SDD adherence, updated for August 10

The August 9 conformance review named seven gaps against `AGENTS.md`. Since
then, the design chain (v1 → v2 → v3) has closed three by discipline (the four
halts in v3) and left four still open. Two new gaps show up in the design's
own execution.

**Closed since Aug 9 (through v3's four halts):**

- Vocabulary evolution routed through `vocabulary_change_required` (H-1
  ratified). `Verdict` enum lands as a proper vocabulary proposal, not a
  struct-field append. Rule 2 honored.
- Two lexicons collapsed into one closed set at the oracle boundary (H-3
  ratified). Runner reads shared strings from `assay/swebench._HARNESS_REASONS`.
- Observation contract for the wire-check gate at N=300 Lite (H-4 ratified).
  Rule 9 honored for the wire-check specifically.

**Still open from the Aug 9 review:**

- **Gap 1 — no Sprint 0 vocabulary session for the SWE-bench sub-topology.**
  Nine tags grew sprint by sprint. Remedy proposed (Vocabulary Session,
  retrofit as `signals/0.2.json`); nothing scheduled. Load-bearing.
- **Gap 2 — deletions.** `scripts/assay_full_run.py` and three others deleted
  in sprint 146. Deletion carve-out lives in the project roadmap; not
  promoted to a kit-level ADDENDUM under `sdd-kit-2/ADDENDUMS.md`.
- **Gap 3 — string-literal contracts not in canonical home registry.**
  `WORKING_AGREEMENT.md` has no section for view names, event kinds, decision
  enum values. F10 (August 8) hoisted sixteen bare view-name literals into
  six module-level constants after the fact.
- **Gap 6 — stringly-typed cell dispositions.** `source == "run"`, `"salvage"`,
  `"error"` at `scripts/assay_swebench_confirmatory.py:186`. No `CellSource`
  enum. A typo produces an empty aggregation, not a `NameError`.

**Newly observed (this review):**

- **Gap 8 — the confirmatory runner bypasses the assay control plane
  (`run_suite`).** Finding 1 above. The whole SDD discipline of "generic
  primitives, project-specific rules" is fought when a bespoke 837-line
  script re-implements the generic outer loop.
- **Gap 9 — the matrix arms are five near-identical factories where one
  parametric factory + data would suffice.** Finding 2 above. Every future
  same-topology arm adds a factory instead of a row.

Weighted by load-bearing rule: about 80 percent — down from the August 9
review's 85, because the design's answer to the runner shape is more of the
same (v3 grows the runner to ~200 lines of new changes, no simplification).

---

## The SWE-bench oddity, engaged briefly

The user is right that SWE-bench's shape is oddly specific for a benchmark that
carries so much weight in the field. The contract is narrow:

- Output is a unified git diff against a specific base_commit.
- Applied via `git apply` inside a Docker image pinned to the instance.
- Tests are pytest, Python only.
- Grade is a subprocess call to Docker to run pytest against `test_patch`.

The shape came from what Princeton had at hand in 2023 — pull requests as
ground truth, Docker for reproducibility, pytest as the check. That worked
well enough to define the field, but it means every benchmark contender is
building the same wrappers: repo cloning, image pinning, patch parsing,
harness lifecycle, timeout enforcement. The economic weight the benchmark
carries versus the ceremony required to run one instance is out of proportion.

For substrate the shape is workable because SWE-bench fits the
external-grader Oracle pattern cleanly: a topology emits ONE typed
`SelectedPatch` event with `model_patch: str`; the grader runs Docker; the
verdict rides on the Result. Any topology that satisfies that contract is a
valid arm. This is the right abstraction, and it is already in the code.

The place substrate should be leaning into that abstraction is at the arm
side — running structurally different topologies through the same Adapter and
Oracle. Instead the effort has been at the topology side, building richer
selection logic inside one topology. That is finding 8 above, restated: the
work has been building a better solver instead of proving the assay pattern
generalizes.

For the "any Substrate application that fits the parameters can immediately
be assayed" goal: the parameters that fit are already known and small.

1. The topology's `build(case)` returns something that emits `SelectedPatch`.
2. Every arm on a Case consumes the identical `PreparedPayload` (the
   Wave-0-carry discipline).
3. The Oracle grades the emitted patch via the external harness.

The three constraints are enforceable by the type system today
(`PreparedPayload` is a TypedDict; `Arm.build` returns a `Topology`; the
Oracle is generic). The one missing piece: a concrete second arm using a
different topology, to prove the pattern beyond parameterized `swebench_repair_topology`.
A `tool_loop`-based arm at ~50 lines would demonstrate this and turn "any
topology of the right shape" from a claim into evidence.

---

## Nine moves ranked

**1. Run one non-repair arm on SWE-bench.** Concrete: a `tool_loop`-based arm
wrapping `topologies/tool_loop/` with file-read/edit/bash tools on the
`base_checkout`, emitting `SelectedPatch` at end-of-run. About 50-100 lines in
`assay/swebench_matrix.py`. This is the largest engineering-to-signal move:
proves the assay pattern generalizes AND gives the North Star's mechanism
claim a real comparator. Everything else the North Star wants (named
strategies, cockpit dispatch) requires this pattern to be real, not aspirational.

**2. Collapse the five current arms into one parametric factory + a data
table.** `swebench_repair_arm(name, role, *, models, n, max_rounds)` plus a
five-row table. `assay/swebench_matrix.py` shrinks by 100+ lines. Adds a
factory row to add an arm; no code change. This is finding 2 landed.

**3. Fold `assay_swebench_confirmatory.py`'s generic pieces into
`assay/run.py`.** Identify salvage-mode, resume, per-cell wall budget, typed
cell rows as generic assay concerns (they are); extend `run_suite` to carry
them; the runner shrinks from 837 lines to ~200 that is genuinely
SWE-bench-specific (harness wiring, timeout table, verdict reason mapping).
This is finding 1 landed.

**4. Delete or study `swebench_solver_topology`.** Either: (a) commit a sprint
that measures in-topology test-based selection versus harness-only on the
same 300 Lite cases and reports the delta, or (b) retire the topology into
`topologies/swebench_solver/_deprecated/` with a KIT_DIARY entry naming the
retirement reason and the last-live sha. Currently it sits alive as
architectural weight for a study nobody has planned. Ties to postmortem RC1's
underlying cause.

**5. Sprint 0 vocabulary session for the SWE-bench sub-topology.** Retrofit
the nine tags that grew sprint-by-sprint into a locked `signals/0.2.json`
with a rationale doc. Closes SDD Gap 1. Not glamorous; load-bearing per
hard rule 12.

**6. `CellSource` enum + `assay/swebench_errors.py` typed exceptions.**
Together these close SDD Gaps 3, 6, and my finding 4. About 80 lines across
two files. Every write site references the enum; every catch site catches
by type. The runner's `_classify_cell_error` string matching disappears.

**7. Unify the timeout regime.** One per-cell budget derived from the per-repo
grade table; the topology watchdog and the grader timeout both derived from
it. Currently three separate numbers with three lexicons is finding 7.

**8. Collapse the two grading paths.** Delete `SwebenchExtractOnlyOracle` and
`batch_grade_from_records` in the commit that flips `SWEBENCH_BATCH_GRADE`
default to `"0"`. Inline is the only path once the topology is bounded.
Finding 6 landed.

**9. Consider factoring `swebench_repair_topology`'s "best-of-N plus
correction loop" as an `embedded_substrate` sub-topology.** The round-3
solver design at `docs/swebench-solver-design.md:82-86` says this shape is
consumed by three topologies (`swebench_solver`, `coding_flow`,
`code_evolution`). Factoring it via `embedded_substrate` (the
`kernel/composition.py:84` primitive designed exactly for this) removes the
duplicate wiring in the current three and gives future consumers one
contract. Larger change (a week); best done after moves 1-3 land.

---

## The one paragraph

The SWE-bench work is a real Substrate application built on a real Substrate
primitive stack, honoring most of SDD's twelve rules. It under-uses
Substrate at the runner (an 837-line bespoke script where `run_suite` should
carry the load), at the matrix (five factories where one parametric factory
plus data would suffice), and at the arm shape (five variants of one topology
where the North Star wants topologically distinct comparators). It reinvents
one exception taxonomy the substrate hierarchy could have covered by type
rather than by string match. It drags a heavy topology alive without a study
plan, keeps two grading paths without a use case, and enforces three separate
timeouts under three names. The v3 design closes four SDD halts the v2 design
missed, which is real progress; the design does not close the runner-shape gap
or the topology-agnostic-assay gap, which are the two largest. Nine moves
ranked above turn the work from "one bespoke SWE-bench solver dressed as an
assay" into what the North Star at
`docs/NORTH-STAR-2026-08-10-v5.md` names — a benchmark any Substrate topology
of the right shape can plug into, measured through one Adapter and one
Oracle, with the mechanism claim answerable against real comparators rather
than parameterized variants of the same topology.

---

*Sources this review cites, in the order they appear:
`docs/DESIGN-2026-08-10-swebench-confirmatory-revert-v3.md`,
`docs/DESIGN-2026-08-10-swebench-confirmatory-revert-v2.md`,
`docs/DESIGN-2026-08-10-swebench-confirmatory-revert.md`,
`docs/POSTMORTEM-2026-08-10-swebench-topology-drift.md`,
`docs/NORTH-STAR-2026-08-10-v5.md`,
`docs/swebench-first-principles-2026-08-09.md`,
`docs/swebench-solver-design.md`,
`docs/swebench-close-the-loop-roadmap.md`,
`docs/swebench-assay-roadmap.md`,
`docs/adding-a-topology.md`,
`docs/review/REVIEW-2026-08-10-swebench-confirmatory-revert-v2.md`,
`docs/review/REVIEW-2026-08-09-sdd-conformance-swebench-additions.md`,
`docs/review/REVIEW-2026-08-09-swebench-runner-shape-and-walltime.md`,
`substrate/process/BLACKBOARD.md` (tail),
`substrate/src/substrate/api.py`,
`substrate/src/substrate/assay/suite.py`,
`substrate/src/substrate/assay/oracle.py`,
`substrate/src/substrate/assay/run.py`,
`substrate/src/substrate/assay/swebench.py`,
`substrate/src/substrate/assay/swebench_suite.py`,
`substrate/src/substrate/assay/swebench_matrix.py`,
`substrate/src/substrate/topologies/swebench_solver/assemble.py`,
`substrate/src/substrate/topologies/swebench_solver/select_exec.py`,
`substrate/src/substrate/topologies/swebench_solver/select_docker.py`,
`substrate/scripts/assay_swebench_confirmatory.py`,
`substrate/src/substrate/kernel/composition.py`,
`sdd-kit-2/AGENTS.md`.*
