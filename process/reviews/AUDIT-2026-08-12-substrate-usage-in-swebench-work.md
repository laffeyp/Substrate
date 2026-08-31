# AUDIT — Substrate-primitive usage in the SWE-bench work

*Companion to `PAPER-2026-08-12-swebench-failure-and-the-sdd-remedy.md`.
That paper diagnoses SDD adherence. This audit measures the second half of
the same question: to what extent did the SWE-bench work use the primitives
Substrate ships? Every claim carries a citation to `src/substrate/api.py`
or to a specific topology/module at its current-HEAD line number.*

*Reviewer role. This is a specification the build side reads and dispatches
from. No code is edited here.*

*Date: 2026-08-12.*

---

## Verdict

The topology at `topologies/swebench_solver/assemble.py:257`
(`swebench_repair_topology`) is close to correct. The Substrate under-use
lives in the scaffolding around it — the runner, the matrix (pre-Move 2),
the two oracle classes, the DockerTestRunner wiring, and the missing
`bundled.py` registration. Substrate's public surface exports about 55
primitives; the SWE-bench work uses roughly 15 of them. Eleven more are
available and were skipped, some at real cost.

The rebuild is not literally from scratch. Roughly 60 percent of the
current SWE-bench code is right and preserves; roughly 40 percent is
scaffolding that should be replaced with primitives already shipped.

---

## Section 1 — Substrate primitives, used and skipped

### 1.1 Used correctly

`TopologyBuilder`, `producer_kind`, `initial`, `view`, `KindBuffer`,
`PerKindLatest`, `Once`, `PerEvent`, `threshold_count`,
`quiescence_with_watchdog`, `any_of`, `Runtime`, `Suite`, `Arm`, `Case`,
`ExternalGraderOracle`, `Verdict` (post H-1). Fifteen primitives, used at
the shapes their documentation names. The topology's structural bones sit
here.

### 1.2 Available and skipped, ranked by cost

**1. `run_suite` at `assay/run.py:101` — the largest miss.**
Every other assay in the tree uses this 12-line outer walker. The SWE-bench
work replaced it with a 837-line bespoke script,
`scripts/assay_swebench_confirmatory.py`. Roughly 60 percent of that
script's lines re-implement generic assay concerns:
`asyncio.Semaphore` around cell dispatch, per-cell `asyncio.wait_for`,
salvage-mode regrade, checkpointed resume, cell-row JSONL writing,
batch-grade dispatch, tier verification. Sprint 144a's docstring at
`docs/swebench/swebench-close-the-loop-roadmap.md` § "Group A" is a punch list of
"parity gaps against `bench_coding.py`" — two runners converging by hand.

**2. `register_topology` in `topologies/bundled.py`.**
The `BUNDLED` dict at `bundled.py:92` iterates registered factories. Every
other topology appears in it. `swebench_repair` and `swebench_solver` do
not. Consequence: `substrate run --topology swebench_repair` fails.
`substrate tail`, `substrate inspect`, `substrate demo replay swebench_repair`
all unreachable. `code_review/__init__.py` is the canonical template per
`docs/adding-a-topology.md` § "Add it to the catalogue"; SWE-bench skipped
the step.

**3. `embedded_substrate` at `kernel/composition.py:84`.**
The composition primitive designed to factor "best-of-N + correction loop"
once across three consumers: `swebench_solver`, `coding_flow`,
`code_evolution`. `docs/swebench/swebench-solver-design.md:82-86` names this
explicitly. Zero consumers today. The shared sub-topology got re-implemented
in three places — three copies of `Candidate` / `Verdict` / `Solved` /
`ModelUsage` wiring, three places for the currency-gate or determinism bug
to diverge.

**4. `cancel_all_others` termination policy.**
The `TerminationPolicy` at `api.py:107` designed for the exact
first-candidate-wins shape the repair topology emits. Not used. The
topology emits `SelectedPatch` and every other drafter finishes its own
draft — wasted model calls per cell. At N=3, roughly 66 percent of drafter
compute is wasted after the first apply succeeds.

**5. `assert_replayable` at `projections/replay.py`.**
The replay guarantee at the topology boundary. `code_review`'s tests assert
it per `adding-a-topology.md` step 2. `swebench_repair_topology` has no
such assertion. Consequence: the topology's replayability is a claim, not
a check.

**6. `explain_producer`, `trace_ancestry`, `first_divergence`, `view_at`,
`decisions_between` at `projections/inspect.py`.**
The post-run debugging primitives. Every SWE-bench postmortem this month
reconstructed causality by reading commit logs and grepping cell rows.
`explain_producer` walking the record backwards from a `SelectedPatch`
event would have answered "why did this candidate get picked" in one call.
`first_divergence` comparing a working run against a broken one would have
localized the drift between June 27's shape and August 9's in one call.
Neither was tried.

**7. `narrate` / `topology_graph` / `run_graph` at `projections/narrate.py`
and `projections/graph.py`.**
The projections `substrate-ui` renders. `assay_swebench_confirmatory.py`
writes its own cell-row JSONL and its own report layer. `topology_graph`
on the repair topology would render the six-arm matrix in the browser;
nothing renders it. `narrate` on a cell's record would produce the
in-vocabulary prose the SDD Rubber Duck Pass wants; the pass runs against
the Signal Report instead.

**8. `attach` / `LiveRecord` at `projections/attach.py`.**
Live observation of a run in flight. The confirmatory runs for hours with
no live UI. `substrate-ui`'s follower half of the loop exists; no one
wired it to a swebench sweep. Consequence: mid-run failures like the
2026-08-09 hang were noticed by the wall clock, not by the tool.

**9. `content_hash` / `canonical_bytes` at `encoding.py`.**
The record's canonical form. The preregistration gate hashes the arms
fingerprint but does not hash the record. There is no post-run identity
check for a silent drift between two ostensibly identical runs.

**10. `run_conformance` / `ConformanceReport` at `conformance/conformance.py`.**
The v1.0 release gate. Not run against the SWE-bench sub-topology. Runs
clean against everything else.

**11. Typed `SubstrateError` hierarchy at `errors.py`.**
The runner's `_classify_cell_error` at
`scripts/assay_swebench_confirmatory.py:146-183` string-matched
`repr(exc)` for `"docker"` and `"git"` for six weeks. F4 landed
`swebench_errors.py` yesterday at commit `2f311d6`; the pattern the
`SubstrateError` hierarchy exists to teach was rediscovered locally
instead of read off `api.py`.

---

## Section 2 — What a correct topology looks like

`code_review/__init__.py` is the canonical template per
`docs/adding-a-topology.md` line 159. Six things it does that
`swebench_solver/assemble.py` should:

**1. One function of the builder.**
`def code_review(b: TopologyBuilder) -> None`.
`swebench_repair_topology` at line 257 does this correctly.

**2. All events are frozen msgspec Structs.**
Correct at `records.py:37-152`.

**3. Model seam via `Responder`, never a specific model.**
Correct. Responders passed in from the arm helper.

**4. Dual-mode: CI stub + real model.**
`code_review` takes `responder=None` and defaults to
`DeterministicResponder(seed=0)` for CI. `swebench_repair_topology` takes
a required `responders: list[Responder]`. Not dual-mode. Consequence: no
CI record, no `substrate run` invocation, no walkthrough demo, no
byte-stable trace in the test suite that pins the topology's shape.

**5. Registered in `bundled.py`.**
Not done. `code_review` is in the `BUNDLED` dict; SWE-bench topologies
are not.

**6. CI record committed + test asserting substance.**
`code_review` ships `records/ci_mode.record` from
`scripts/gen_topology_records.py`. Tests assert `assert_event(rec, "Note")`
and `assert_sequence(...)` per `adding-a-topology.md` step 2 — the claim
happened, not just an event exists. SWE-bench has neither the record nor
the substance assertion.

The topology at line 257 is close to a correct topology. Closing the four
gaps (dual-mode default, `bundled.py` registration, CI record, substance
test) is roughly a two-file change. Half a sprint.

---

## Section 3 — What a correct SWE-bench arm looks like

Six things the scaffolding around the topology should do:

**1. Arm helper returns `Topology`, period.**
`swebench_repair_arm(name, role, *, models, n, max_rounds)` returns an
`Arm` whose `build(case)` returns a topology. No inline Docker wiring, no
responder construction outside the arm's `build`. Data table names the
five current arms. Move 2 landed this yesterday at commit `7359439`; the
shape is right.

**2. Runner is `run_suite` plus SWE-bench-specific helpers.**
Not 837 lines. `bench_coding.py`'s shape at
`scripts/bench_coding.py:251-299` is 40 lines around a `run_suite` call.
SWE-bench-specific needs (salvage mode, per-cell wall budget from the
timeout table, batch-grade opt-in) fold into `assay/run.py` as generic
assay helpers or into named modules the runner imports.

**3. Best-of-N + correction as `embedded_substrate` sub-topology.**
One sub-topology, three consumers. The shape at
`docs/swebench/swebench-solver-design.md:82-86`. Removes duplicate wiring across
`swebench_solver`, `coding_flow`, `code_evolution`.

**4. Oracle is one class, one grade path.**
`SwebenchRecordOracle` inline at `swebench.py:380`. Delete
`SwebenchExtractOnlyOracle` at `swebench.py:515` and
`batch_grade_from_records` at `swebench.py:835`. Move 8's finish.

**5. Termination uses `cancel_all_others` for first-patch-wins.**
Cuts wasted model calls when the first candidate applies. Available at
`api.py:106`.

**6. Post-run debugging via `explain_producer` and `first_divergence`.**
Standardize this in the sprint-close ritual so the next postmortem calls
them rather than reconstructing causality by grep and commit log.

---

## Section 4 — Keep versus remove

### Keep (rationale)

- **`swebench_repair_topology` at `assemble.py:257`.** Shape is right;
  four gaps to close (Section 2). Preserve.
- **`applier.py`** — the SEARCH/REPLACE applier. Highest-risk deterministic
  component per `swebench-solver-design.md §4b`. Tiered-match contract
  works; preserve exactly.
- **`assay/swebench.py`'s bridge to the external harness** —
  `verify_constants`, `firewall_check`, `read_resolved`, `run_swebench_one`.
  Correct at boundaries Substrate does not cover.
- **`assay/swebench_suite.py`'s Adapter** — `prepare_swebench_case`,
  `PreparedPayload`, `swebench_suite`, `_mother_clone` cache. Right shape.
- **`assay/swebench_errors.py`** — typed hierarchy landed 2026-08-11 at
  commit `2f311d6`. Correct.
- **`assay/oracle.py`'s `Verdict` enum** — H-1 ratified 2026-08-10.
  Correct.
- **`substrate/adapters/rate_limit.py`** — the rate-limit shim is
  Substrate-level and generalizes to any provider. Preserve at its
  current location.
- **`assay/swebench_timeouts.json`** — data, not code. Preserve.
- **`assay/swebench_matrix.py` post-Move-2** — parametric factory + data
  table shape. Preserve.
- **`container_arm` (F8)** at `swebench_matrix.py:110` — one-producer arm
  touching the same six external boundaries as the repair path, built with
  the discipline the holistic review named. Works. Preserve as the second
  topology-shape proof.
- **Pre-registration files under `docs/preregistrations/`** — the
  discipline is right; numbers stay.
- **All tests under `tests/test_assay_swebench*`, `tests/test_swebench_*`,
  `tests/test_adapters_ensemble.py`, `tests/test_rate_limit.py`** — they
  encode contracts already earned.

### Remove or move

- **`scripts/assay_swebench_confirmatory.py`** (837 lines) — replace with
  a thin runner around `run_suite` plus SWE-bench helpers folded into
  `assay/run.py`. `bench_coding.py`'s shape.
- **`SwebenchExtractOnlyOracle`** at `swebench.py:515` — delete under the
  light topology.
- **`batch_grade_from_records`** at `swebench.py:835` — delete under the
  light topology; batch-grade path retires with `SwebenchExtractOnlyOracle`.
- **The heavy topology** (`swebench_solver_topology_with_test_selection`)
  — already retired at commit `3883973`. Verify the five files under
  `topologies/swebench_solver/` that supported it — `select_exec.py`,
  `select_docker.py`, `select_regression.py`, `repro_base_validate.py`,
  `reproduction.py` — are unwired. Anything unwired moves to
  `topologies/swebench_solver/_deprecated/` with a KIT_DIARY entry per
  hard rule 12 (audit trail preserved; not a raw delete).

---

## Section 5 — The one non-obvious call

"Remove all this code and start from scratch" is not literally right. The
topology at line 257 is close to correct. The applier is correct. The
bridge to the harness is correct. The Adapter is correct. The tests encode
contracts already paid for — the applier's tiered-match discipline, the
firewall parser's fail-closed shape, the mother-clone cache, the
pre-registration hashes.

A literal from-scratch rebuild throws away those contracts and repeats
their earning. Roughly six weeks of prior work would run again to
rediscover the same shapes.

A clean rebuild that preserves what works and replaces what does not is
the counterfactual timeline in
`PAPER-2026-08-12-swebench-failure-and-the-sdd-remedy.md` Section 6:
Sprint 0 through Sprint N, roughly two weeks at SDD pace. The rebuild's
work is:

- Fill the four gaps between `swebench_repair_topology` and a correct
  topology (dual-mode default, `bundled.py`, CI record, substance test).
- Rewrite the scaffolding to use `run_suite` and `embedded_substrate`.
- Delete the two-path grading paths and the heavy topology's satellite
  files.
- Land the missing kernel primitive (`producer_kind` resource budget).
- Fold the six external-boundary defenses into a bridge mapping section
  in `WORKING_AGREEMENT.md`.

The sprint chain is specified in the companion document
`ROADMAP-2026-08-12-swebench-rebuild-sprint-chain.md`.

---

## Section 6 — The load-bearing paragraph

Substrate ships 55 primitives on `api.py`; the SWE-bench work uses 15 of
them at their correct shapes. Eleven more sit on the same file, documented,
tested, and applicable — `run_suite` for the outer walker, `embedded_substrate`
for the shared sub-topology, `cancel_all_others` for the first-patch-wins
termination, `explain_producer` / `first_divergence` for post-run
debugging, `narrate` / `topology_graph` for the projections the UI wants,
the typed `SubstrateError` hierarchy for what the runner classified by
string match. The topology at line 257 is roughly a correct topology; the
scaffolding around it is where Substrate was replaced with hand-written
alternatives that grew sprint by sprint. The rebuild uses what ships,
preserves what works, and deletes the alternatives. Roughly two weeks at
SDD pace closes the gap.

---

*Sources: `src/substrate/api.py`; `src/substrate/kernel/composition.py`;
`src/substrate/kernel/topology.py`; `src/substrate/projections/*.py`;
`src/substrate/conformance/conformance.py`; `src/substrate/errors.py`;
`src/substrate/topologies/bundled.py`;
`src/substrate/topologies/swebench_solver/assemble.py`;
`src/substrate/topologies/swebench_solver/applier.py`;
`src/substrate/topologies/code_review/__init__.py`;
`src/substrate/assay/run.py`; `src/substrate/assay/oracle.py`;
`src/substrate/assay/suite.py`; `src/substrate/assay/swebench.py`;
`src/substrate/assay/swebench_suite.py`;
`src/substrate/assay/swebench_matrix.py`;
`src/substrate/assay/swebench_errors.py`;
`src/substrate/adapters/rate_limit.py`;
`scripts/assay_swebench_confirmatory.py`;
`scripts/bench_coding.py`;
`docs/adding-a-topology.md`; `docs/swebench/swebench-solver-design.md`;
`docs/review/PAPER-2026-08-12-swebench-failure-and-the-sdd-remedy.md`;
`docs/review/REVIEW-2026-08-10-swebench-holistic.md`;
`docs/review/REVIEW-2026-08-11-swebench-re-review.md`.*
