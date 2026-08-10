# REVIEW — DESIGN-2026-08-10-swebench-confirmatory-revert-v2 (2026-08-10)

*Target: `substrate/docs/DESIGN-2026-08-10-swebench-confirmatory-revert-v2.md`.
Companions read: `POSTMORTEM-2026-08-10-swebench-topology-drift.md`,
`DESIGN-2026-08-10-swebench-confirmatory-revert.md` (v1 on disk),
`substrate/process/BLACKBOARD.md` tail, and the code the design cites.
Reviewer role: findings for the build side; no patches written here.
Lens: sdd-kit-2 AGENTS.md discipline and the vocabulary-as-contract rule.*

---

## Verdict

The diagnosis is right and the target shape is right. The heavy topology duplicates
the grader; the light `swebench_repair_topology` already ships at
`assemble.py:257`; the third grade state has a real name and belongs in the vocabulary;
the grader must own its containers; the report must publish three numbers. The
five-arm matrix rewiring holds together, and the one-commit-per-step cadence is the
right cadence for keeping the confirmatory bisectable.

The design under-delivers on the discipline the postmortem itself calls for. Every
line-number citation is stale. The new `Verdict` enum is a vocabulary change routed
through a struct-field append. The wire-check gate contradicts itself on sample
size. Nothing structural stops the heavy topology from being rewired. The runner's
enforcement primitive for per-cell wall-clock is unspecified. Four halts and four
commits close that gap before code lands.

---

## Findings, ranked by consequence

### 1. Every code citation is off by roughly 40 lines

The design cites `swebench_repair_topology` at `assemble.py:217`. Actual location:
line 257. `swebench_solver_topology` is cited at line 398; actual line 438.
`_first_patch_selector_factory` is cited at line 158; actual line 198.
`SwebenchRecordOracle` at `swebench.py:380` names the class opening; the `.grade`
method sits at line 415. `SwebenchExtractOnlyOracle` opens at line 515; its `.grade`
is at line 528. The pattern says the doc was written against a snapshot roughly one
commit stale.

This is postmortem contributing factor CF4 — "I did not re-read the git history" —
reproduced inside the document that names CF4. A reader who follows the anchors will
open the wrong region and misedit. Re-anchor every path:line reference against
current HEAD before merge.

### 2. The `Verdict` enum is a vocabulary change and must halt

`assay/oracle.py:35` defines `Result` — the shared oracle contract every assay in the
tree reads. Growing it a load-bearing enum called `Verdict` with three named states
is precisely the case AGENTS.md hard rule 2 covers: *never invent tags; halt with
`vocabulary_change_required` and route through one of the eight supervised evolution
types in `grammar/PRINCIPLES.md`.* The design merges the enum inline as an additive
struct field with backward-compat cladding.

The correct sequence is halt, propose the tag under the matching evolution type,
Architect sign-off in `BLACKBOARD.md ## Decisions`, then land the code. This is the
substrate's own discipline, and the postmortem is a record of what silent vocabulary
growth costs. The kit exists to hold this line.

### 3. `passed: bool` and `verdict: Verdict` in one Result is drift by construction

The design keeps `passed: bool` alongside `verdict: Verdict` with the invariant
`passed == (verdict == RESOLVED)` maintained by convention. Two fields, one fact,
kept in sync by hand. Every future consumer picks one; some pick both; the two drift
the first time a code path forgets. Ruff and mypy will not see it. This is the
retyped-literal drift pattern the substrate has been fighting.

Two clean options: (a) drop `passed` in the same commit and migrate every reader to
`verdict == RESOLVED` — the audit shows a small blast radius; (b) keep the name and
make `passed` a `@property` derived from `verdict` so one field holds the fact.
"Backward compat" as written ships the drift.

### 4. Two lexicons for one closed set of failure reasons

Oracle reasons in the design: `harness_timeout`, `container_crash`, `docker_error`,
`harness_error:<class>`. Runner `source` closed set:
`run`, `salvage`, `timed_out`, `docker_error`, `git_error`, `firewall_violation`.
The same underlying event carries two names — `harness_timeout` versus `timed_out`,
`container_crash` versus `docker_error`.

A report reader chasing a `no_verdict` with source `timed_out` cannot pattern-match
back to the oracle's `harness_timeout` without a translation table. Define the closed
set once at the oracle boundary, echo the strings unchanged in the runner rows, and
delete the second lexicon. This is the vocabulary-as-contract rule applied to strings
rather than tags.

### 5. `Verdict.RESOLVED / NOT_RESOLVED` leaks SWE-bench language into a general oracle

`assay/oracle.py:Result` is called from every assay in the tree, not only SWE-bench.
An arithmetic assay produces `verdict = RESOLVED` for a correct answer, which reads
wrong in English and drifts on meaning. Two ways out: rename the enum to
`PASS / FAIL / NO_VERDICT` — which also aligns with the pre-existing `passed` field
name and makes finding 3's rename mechanical — or scope the enum to
`SwebenchVerdict` at `assay/swebench.py` and leave `oracle.Result` shape-general
with a per-assay `verdict: Any` typed by the specific oracle. Option (a) is cleaner
because it collapses the two-field problem in finding 3.

### 6. The wire-check gate contradicts itself on N

Step 5 sets the wire-check at "n=20 instances first." The Discipline for prevention
section requires a "runs 300 Lite wire-check gate before Verified fires." The doc
runs both numbers past the same reader.

N=20 at ~35 percent resolve gives a Wilson 95 percent CI of about ±21 points. A
drift from 36 percent to 25 percent will not clear that CI. The June 27 shape is
108/300 = 36.0 percent ± 5.4 points — a real test of shape. N=20 is a smoke test;
call it that and reserve it for "did the topology emit anything." Require N=300
Lite as the gate on Verified spend, matching what June 27 actually produced.

### 7. The `SwebenchExtractOnlyOracle` placeholder is a fourth verdict state the design does not name

`SwebenchExtractOnlyOracle.grade` at `swebench.py:515-585` returns `passed=False`
unconditionally with `detail=f"deferred: patch={len(patch)}b for {instance_id}"`
during the sweep. The batch grade then reconstitutes the real grade afterwards.
Between the two steps, the record carries a placeholder that is neither RESOLVED,
NOT_RESOLVED, nor NO_VERDICT — it is DEFERRED, a fourth state the design's three-state
enum has no room for.

Two implementations. Add `Verdict.DEFERRED` to the enum and have the batch grade
overwrite it with the final verdict once known; or drop the extract-only oracle
entirely under the light topology, since per-cell inline grade at 1-5 minutes is
tractable (the design's own claim under the runner contract). The second is simpler
and matches "batch grade is optional and off by default." Pick one and record it.

### 8. Nothing prevents the heavy topology from being rewired

The design keeps `swebench_solver_topology` in the codebase "for research use." No
naming gate, no `include_test_selection=True` argument on the arm helper, no unit
test in `tests/test_assay_swebench_matrix.py` asserting that every arm factory
produces the light topology. The postmortem's RC2 — *"the working topology exists but
no arm calls it"* — reactivates the moment a well-intentioned refactor pipes the
heavy one back through the matrix.

Concrete gates that cost minutes: rename to
`swebench_solver_topology_with_test_selection` so the cost is visible in the call
site; require an explicit `include_test_selection: bool = False` kwarg on the arm
helper for future opt-in; add one test that dispatches `_build_solver_arm_from_payload`
and asserts the built topology's producer_kinds do not include `select_exec`. Each
closes RC2 in the type system rather than in a doc.

### 9. `run_swebench_one`'s wall-clock enforcement primitive is unspecified

The design says the function "enforces a wall-clock deadline itself, not the harness"
and on deadline `docker kill`s the container. It does not say how. Under
`ThreadPoolExecutor`, Python thread cancellation is cooperative — a `threading.Timer`
firing `docker kill <container_name>` externally works; `asyncio.wait_for` inside a
worker thread does not. `subprocess.run(..., timeout=T)` around a shell-invoked
harness step plus `docker kill` in the `except subprocess.TimeoutExpired` block is
the safe primitive.

Spec it in the design. Otherwise the coder invents it, gets it half right, and
the sympy 90-minute hangs return at scale.

### 10. `SWEBENCH_BATCH_GRADE`'s default flip belongs in the diff

Current code at `scripts/assay_swebench_confirmatory.py:223`:
`BATCH_GRADE = os.environ.get("SWEBENCH_BATCH_GRADE", "1") == "1"`. Batch grade is
on by default. The design says off by default. That is a one-character change,
`"1"` → `"0"`, and it belongs in the runner-change commit or in the drift watchlist.
Silence ships production with batch grade still on.

### 11. `swebench_repair_topology`'s watchdog default is 60 seconds, not 900

Signature at `assemble.py:266`: `watchdog_seconds: float = 60.0`. The design sets
Pass 1 to W=900s (15 min). Two places to record this: change the default in the
topology signature, or make the arm helper pass the value explicitly at build time.
If neither happens, cells silently use the 60-second watchdog, false-time-out, and
the light-topology run drifts from the June 27 shape. Name the value in the arm
helper and pin the number in the pre-registration.

### 12. `_classify_cell_error` already halts on unclassified — the current shape is what the design wants

`_classify_cell_error` at `scripts/assay_swebench_confirmatory.py:146-183` returns
`(reason, halt_bool)`. Line 183 returns `(_ERROR_UNCLASSIFIED, True)` — halt. The
design says "extend the closed set as new failure modes appear." Match the current
code's language: the fix does not need to change the classifier's default, only add
new named reasons if new modes appear during Lite calibration. This is a clarity
edit; the underlying discipline is already in the code.

Note also the 2026-08-09 comment at line 175: FirewallViolation was demoted from
halt to flake because "one mis-parsed django test id can't take down 1500 cells."
That downgrade is real and needs a line in the design's Discipline for prevention
section — a flake can hide a data bug. Either flip it back or document the
compensating check (the report counts firewall violations end-of-run; who reads it).

### 13. Discipline-for-prevention rule 3 is aspirational

*"Every topology stage declares a resource budget. This is a follow-on kernel change
and lands in a separate design doc."* Meaning the producer_kind budget contract the
postmortem faults `select_exec` for lacking is not enforced by this landing. The
current fix reroutes around the bug rather than closing the gap. Fair to defer, but
name the owner and the date: "kernel change owned by X, targeted for sprint N." A
prevention rule without a landing schedule is a hope.

### 14. Pass 1 shape (500 × 3 × 1) reproduces the failing run's cell count without stating why

Three trials estimate cross-run variance; N=500 estimates arm-effect. Running both
at full scale for a single arm produces 1500 cells — the same wall-clock shape the
postmortem calls out. Consider N=500 × 1 trial for Pass 1's arm number, with
variance estimated from the Lite calibration pass at Step 5 (which already produces
per-arm verdict distributions at N=20 × 5 arms = 100 cells; move Step 5 to N=300
per finding 6 and the variance number is well-earned).

If 3 × 500 is correct, state what it buys. Three-trial McNemar for Pass 1 alone
reads as belt-and-braces given Pass 2 will run the whole matrix.

### 15. Observation contract missing (AGENTS.md hard rule 9)

Grading and reporting are product behavior. Hard rule 9 requires a behavior-touching
sprint to declare an observation contract: input fixtures (which N Lite instances
by ID), expected log substrings (`"108 resolved"`, `"0 unclassified halts"`),
expected runtime signals (`RepairSummary` count, `SelectedPatch` count per cell),
and expected artifacts (three-number headline present, verdict counts per arm,
publish-refusal branch fires below threshold).

The design's Step 5 wire-check is close to this but not typed as one. Reframe it as
`## observation contract` in the corresponding sprint card. Without it the
wire-check is narrated intent, not gradable.

### 16. One residual negative construction in the prose

*"Not a single opaque `run_swebench(all_predictions)` call. Sequential loop with a
thread pool…"* Recast to positive per your writing rule: *"The batch grade is a loop
over `run_swebench_one` under a thread pool of `CONCURRENCY` workers. Each worker
owns its container and its deadline."* Same content; no rejected shape named.

The rest of the doc reads clean of "not X" / "Non-goals" / "What NOT to do"
constructions, which is the target.

---

## What the doc gets right

The mechanism call is correct. `select_exec_factory` at
`topologies/swebench_solver/assemble.py:126` runs `asyncio.gather` over every
applied patch's Docker test run — up to six concurrent DockerTestRunner calls per
cell — and the grader then runs a seventh over the winning patch. RC1 tracks the
code. The light topology at line 257 sits there ready with the same
`PreparedPayload` shape, tested, proven by KIT_DIARY entry 26 at 108/300 on
Lite. The five-arm matrix restructure holds together: same topology across arms
means the delta between arms measures the mechanism, which is what Pass 2's
equivalence-form claim needs. The one-commit-per-step cadence keeps the confirmatory
bisectable.

The three-number headline (N attempted, M graded, K resolved) with the
publish-refusal branch below a graded-rate threshold is the right shape for a
number that has to survive external scrutiny.

---

## Four halts before code

1. **Route `Verdict` through `vocabulary_change_required`.** File the halt in
   `BLACKBOARD.md ## Surfaced for review`. Propose the tag under the matching
   evolution type from `grammar/PRINCIPLES.md`. Wait for Architect sign-off in
   `## Decisions`. Then land the enum. This is the load-bearing SDD move on the whole
   design.

2. **Decide `passed` versus `verdict` in one commit.** Either drop `passed` and
   migrate readers, or make it a derived `@property`. No parallel-fact discipline
   debt.

3. **Pick one closed set of failure-reason strings.** Define it at the oracle
   boundary. Echo the strings unchanged in the runner rows. Kill the
   `timed_out` / `harness_timeout` / `container_crash` / `docker_error` mixture
   before the code ships.

4. **Rewrite Step 5 as an observation contract at N=300 Lite.** Name the expected
   verdict counts, the expected log substrings, and the expected signal-tag counts.
   Match the June 27 shape (108/300 = 36 percent, five grade errors) with a real CI
   around it. Fold the "300 Lite" wording from Discipline for prevention into
   Step 5 so the doc reads to one sample size.

## The rest is mechanical

Re-anchor every path:line reference. Flip `SWEBENCH_BATCH_GRADE` default to `"0"`.
Set the arm helper to pass `watchdog_seconds=900`. Rename the heavy topology and
add the matrix-arm assertion that pins the light one. Spec
`subprocess.run(..., timeout=T)` + `docker kill` as `run_swebench_one`'s deadline
primitive. Add `Verdict.DEFERRED` or drop `SwebenchExtractOnlyOracle` under the
light path. Recast the one negative sentence. State the reason for three trials or
drop them. Give discipline-rule 3 an owner and a date.

The design v2 has the right target with the right cadence. Halt on the four items
above before any code lands, then run the seven-step landing sequence, then fire
the N=300 Lite wire-check. The number the confirmatory produces is credible when
the vocabulary under it is stable, the strings under it are shared, the reader can
tell one state from four, and the fix does not ship the same drift shape that broke
the run.

---

*Sources read to compose this review:
`substrate/docs/DESIGN-2026-08-10-swebench-confirmatory-revert-v2.md`,
`substrate/docs/DESIGN-2026-08-10-swebench-confirmatory-revert.md`,
`substrate/docs/POSTMORTEM-2026-08-10-swebench-topology-drift.md`,
`substrate/process/BLACKBOARD.md` (tail),
`sdd-kit-2/AGENTS.md`, `sdd-kit-2/README.md`, `sdd-kit-2/CLAUDE.md`,
`substrate/src/substrate/topologies/swebench_solver/assemble.py`,
`substrate/src/substrate/assay/oracle.py`,
`substrate/src/substrate/assay/swebench.py`,
`substrate/src/substrate/assay/swebench_matrix.py`,
`substrate/src/substrate/assay/swebench_suite.py`,
`substrate/scripts/assay_swebench_confirmatory.py`,
`substrate/src/substrate/topologies/swebench_solver/records.py`.*
