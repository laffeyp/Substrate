# REVIEW — SWE-bench work, re-review after the 2026-08-10/11 landings

*Companion to `docs/review/REVIEW-2026-08-10-swebench-holistic.md` (nine ranked
moves against Substrate + SDD + North Star). This review reads the twelve
commits that landed between yesterday's holistic and now, plus the tail of
`process/BLACKBOARD.md`, and reports what closed, what half-closed, what
remains, and what the N=300 wire-check surfaced that no prior review named.*

*Sources read: `git log --oneline` since commit `265e050` (the holistic
review); `docs/DESIGN-2026-08-11-responder-rate-limit-shim.md` (new today);
`src/substrate/assay/swebench_errors.py` (new); `src/substrate/adapters/rate_limit.py`
(new); the updated `src/substrate/assay/swebench_matrix.py` (383 lines,
`container_arm` added), `src/substrate/assay/swebench.py` (`_HARNESS_REASONS`
closed set at line 76, `run_swebench_one` at line 397, `batch_grade_from_records`
at line 835), `src/substrate/assay/oracle.py` (`Verdict` enum landed,
`Result.reason` now a first-class field at line 93),
`scripts/assay_swebench_confirmatory.py` (837 lines still,
`SWEBENCH_BATCH_GRADE` default now `"0"`), and
`process/BLACKBOARD.md ## Surfaced for review` + `## Decisions` (2026-08-11
Architect ratifications).*

---

## Verdict

The 2026-08-10 design chain executed cleanly. Seven commits landed the four
v3 halts, promoted `reason` to a first-class `Result` field after N=300 caught
a shape leak, closed one open SDD gap from the August 9 conformance review,
and shipped the first structurally distinct SWE-bench arm the North Star had
been asking for. The wire-check at N=300 Lite (H-4) fired and surfaced a
provider-rate-limit failure the topology was silently absorbing as
"no model_patch"; the day's second design and two commits closed the gap.
Six of the nine moves the holistic review ranked have shipped or partially
shipped.

Five moves stand open. Four are the same shape as the holistic review named
them; one — Move 3, folding the runner's generic pieces back into `run_suite`
— grew during the week because every landing added lines to the runner and
none subtracted. The heavy topology got a longer name but no study plan and
no retirement date.

---

## What closed since the holistic review

### Move 1 — structurally distinct arm on SWE-bench (LANDED, 2f311d6)

`container_arm` at `swebench_matrix.py:110` wraps `solve_in_container` — a
read/edit/bash tool loop inside the eval image that emits `SelectedPatch`
via a one-producer topology (`_backend_topology` at line 77, `solve` producer
kind, terminates on `threshold_count("SelectedPatch", 1)` with a
`quiescence_with_watchdog(seconds=3600.0)` backstop). `host_arm` at line 100
is a second non-repair arm running the same one-producer shape against a
host clone. The matrix test in `tests/test_assay_swebench_matrix.py` pins
`producer_kinds == ["solve"]` so a future refactor that silently routes
these through repair machinery trips a red bar in CI.

This turns the assay roadmap's central claim — *any topology of the right
shape is a valid SWE-bench arm* — from a docstring at
`docs/swebench/swebench-assay-roadmap.md:5-8` into two working arms of structurally
different topologies. It is the largest engineering-to-signal move the
holistic review ranked, and it shipped.

### Move 6 — typed exception hierarchy (LANDED, 2f311d6)

`src/substrate/assay/swebench_errors.py` introduces `SwebenchRunnerError`
as a `RuntimeError` subclass and five typed children: `DockerDaemonError`,
`ContainerCrashed`, `GitOperationFailed`, `HarnessTimeout`, `HarnessError`.
Each carries a class-level `reason` string from the shared `_HARNESS_REASONS`
closed set at `swebench.py:76`. The runner's `_classify_cell_error` at
`scripts/assay_swebench_confirmatory.py` catches typed exceptions first;
the pre-F4 `if "docker" in msg or "container" in msg` string-repr fallback
still exists for legacy paths. The module docstring names the H-3 lexicon
(one string set shared by the raise-sites, the runner rows, and the oracle's
`Verdict.NO_VERDICT.reason` field) and calls out the pattern Substrate's
own hierarchy exists to eliminate.

`ProviderRateLimited` lives at `substrate.adapters.rate_limit` and stays out
of `SwebenchRunnerError` because the shim is assay-agnostic — a note in the
new file makes the boundary explicit rather than papering it with a wrapper
subclass no raise-site uses. That is the right call.

### v3's four halts (H-1, H-2, H-3, H-4) landed in six commits

`e5d5bfc` — `Verdict` enum (`PASS`, `FAIL`, `NO_VERDICT`) at
`oracle.py:36`. `Result.passed` becomes a `@property` returning
`self.verdict is Verdict.PASS` at line 100. One field, one fact. H-1 and H-2
closed.

`765400d` — `_HARNESS_REASONS` closed set at `swebench.py:76`
(`REASON_TIMED_OUT`, `REASON_CONTAINER_CRASHED`, `REASON_DOCKER_ERROR`,
`REASON_HARNESS_ERROR`, `REASON_GIT_ERROR`, `REASON_FIREWALL_VIOLATION`).
`run_swebench_one` at line 397 owns per-instance container lifecycle and
wall-clock enforcement via `subprocess.run(..., timeout=T)` plus
`docker kill` in the `except subprocess.TimeoutExpired`. Runner reads the
same strings verbatim on cell rows. H-3 closed.

`97c1eb7` — matrix arms build the light topology
(`swebench_repair_topology`); the heavy one renamed
`swebench_solver_topology_with_test_selection`. Every arm helper passes
`include_test_selection=False`. Test pins the producer_kinds. Part of the
v2-review Finding 8; the rename half of it.

`b5f5961` — runner writes typed `verdict` + `reason` per cell row.
`SWEBENCH_BATCH_GRADE` default flipped from `"1"` to `"0"` at
`scripts/assay_swebench_confirmatory.py:256`. Batch grade stays available
as opt-in.

`140a900` — report gains the three-number headline (N attempted, M graded,
K resolved) with verdict and reason counts per arm. Publish-refusal branch
fires below the graded-rate threshold.

`57468a2` — `reason` promoted to a first-class `Result` field at
`oracle.py:93` after N=300 caught a shape leak: earlier readers were parsing
`reason` back out of `detail`, which drifted the first time a caller wrote
`detail` without the reason prefix. Field lives now; no parsing.

### SDD Gap 7 closed (4fb4eaf)

The runner pre-flights every declared model with a live ping and halts if
any model returns dead. This closes the last outstanding gap from the
2026-08-09 conformance review (`verify_model_tags`, Gap 7 there). External
model tags now have the same runtime verification the SDK constants have
had since sprint 143's bridge mapping.

### Move 4 — half-closed (rename landed, no study plan)

The heavy topology is now `swebench_solver_topology_with_test_selection`.
The name makes the cost visible at every call site. Nothing yet retires it,
schedules a study of in-topology test selection against harness-only, or
moves it to `_deprecated/`. Alive-for-research without a research plan is
still the shape.

### Move 8 — half-closed (default off, code still lives)

`SWEBENCH_BATCH_GRADE` default is `"0"`. `SwebenchExtractOnlyOracle` at
`swebench.py:515` and `batch_grade_from_records` at line 835 still exist.
The two grading paths coexist; the second is opt-in.

---

## What the wire-check surfaced

The observation contract at N=300 Lite (H-4) earned its keep on the first
firing. Ollama Pro-tier throttled 3337 of 4088 HTTP calls — 82 percent —
to 429 during the run. Every multi-call arm collapsed to zero passes; only
the single-call arm survived. The topology absorbed the failure quietly: a
throttled cell wrote the same "no model_patch" row an honest failed try
writes. No signal separated the two.

This is why H-4 mattered. My v2 review argued for N=300 against v2's N=20
smoke test on statistical grounds — a Wilson CI at N=20 spans about ±21
points at 35 percent resolve and cannot distinguish a real drift from
noise. The realized failure was worse than either the postmortem or my
review named: a systemic provider failure hiding as topology silence. An
N=20 gate would have fired 40-100 requests across two arms; the tier cap
would not have been reachable in that budget. N=300 made the throttling
unmissable.

`docs/DESIGN-2026-08-11-responder-rate-limit-shim.md` (new today, 170 lines)
names the fix and two commits landed it.

`c3cf0c9` — `substrate/adapters/rate_limit.py` (200 lines, 5 unit tests) wraps
any `Responder` with a per-`(provider, model)` `asyncio.Semaphore` sized to
the tier's declared concurrent-model cap plus honest `Retry-After` honour on
429 and 503. Retries up to `max_retries` (default 10), then raises
`ProviderRateLimited` — a typed exception the runner catches. `OllamaQuota.free()`,
`OllamaQuota.pro()`, `OllamaQuota.max_tier()`, `OllamaQuota.local()` reflect
Ollama Cloud's 1/3/10 concurrent-model tiers, verified against public docs
and cited in the design.

`3170dc3` — `SWEBENCH_OLLAMA_TIER` env picks the quota at runner startup.
Every `OllamaResponder(model)` construction goes through
`RateLimitedResponder`. Every arm touching the same model shares one gate.
The pre-flight from `4fb4eaf` extended to verify the tier's concurrent-model
cap is at least the number of unique models the run declares; halts on
mismatch. `REASON_RATE_LIMITED` added to `_HARNESS_REASONS` (through a v3-style
`vocabulary_change_required` halt filed and ratified same day per BLACKBOARD
Decisions 2026-08-11).

Shape is provider-agnostic. `AnthropicQuota.tier_1()`, `OpenAIQuota.tier_2()`
plug in as classmethods; no new interfaces. This is Substrate discipline
applied to a boundary the assay layer had left unmodeled.

The lesson worth naming: H-4 was written to prove the confirmatory shape
holds against June 27. It also proved the confirmatory reveals systemic
failures that hide at smaller N. That is the observation contract's second
purpose — a gate wide enough to see what a narrower gate would miss.

---

## What still stands from the holistic review

### Move 2 — the matrix is still five factories where it should be data (OPEN)

`swebench_matrix.py:187-336` still houses five arm factories:
`single_draft_baseline_arm` (187), `n_drafts_no_correction_arm` (209),
`n_drafts_repair_ensemble_arm` (237), `baseline_matched_compute_arm` (266),
`repair_arm` (304). Each is 15-30 lines. Each calls
`_build_solver_arm_from_payload` at line 122 with different values for `n`,
`max_rounds`, and the responder list. The file weighs 383 lines with `host_arm`
and `container_arm` added.

`Arm` at `assay/suite.py:63` is a dataclass taking `name`, `role`,
`build(case) -> Topology`. Five arms differing only in two integers and a
list is one arm factory plus a five-row table, not five factories. A future
same-topology arm adds a row; a future different-topology arm gets its own
factory (which is what `host_arm` and `container_arm` correctly are).

Left open because every landing this week extended what was there rather
than compressing it.

### Move 3 — the runner still bypasses `run_suite` (OPEN, growing)

`scripts/assay_swebench_confirmatory.py` weighs 837 lines. Every commit
this week added to it — the pre-flight ping, the tier verification, the
typed exception catch, the typed cell rows, the three-number headline. None
subtracted.

`assay/run.py:77-112` defines `run_arm_on_case` and `run_suite` — the
generic outer walker for every assay. `bench_coding.py` uses it. The
SWE-bench confirmatory does not. Salvage-mode regrade, resume from
checkpoint, per-cell `asyncio.wait_for` budgets, cell-row JSONL writing,
batch-grade dispatch, typed-error classification, rate-limit tier
enforcement — all of these are generic assay concerns living in a bespoke
SWE-bench script. The right move is either extending `run_suite` to carry
them, or factoring them into named helpers under `assay/run.py` the runner
calls. Neither is scheduled.

This is the largest structural debt still on the table. The runner is
converging on `bench_coding.py`'s shape by hand-copying pieces; the two
runners diverge in every landing that touches only one.

### Move 5 — no Sprint 0 vocabulary session for SWE-bench (OPEN)

Nine tags (`SuspectFiles`, `SuspectElements`, `EditLocations`,
`ReproductionTest`, `TestResults`, `AppliedPatch`, `SelectedPatch`,
`RepairSummary`, `Reproduction`, plus the three sub-topology types
`Solved`, `Draft`, `Candidate`, `Exhausted`) grew sprint-by-sprint from
sprint 133 onward. AGENTS.md hard rule 12 remedy — a Vocabulary Session
retrofit as `signals/0.2.json` — was named in the 2026-08-09 conformance
review and again in yesterday's holistic. Not scheduled. Not blocking any
live sprint, but load-bearing per SDD: the tags that grew after a
resolve-rate was already reported are the tags most likely to have baked
the wrong shape.

### Move 7 — three unreconciled timeout regimes (OPEN, partially framed)

`swebench_repair_topology`'s `watchdog_seconds` defaults to 60 at
`assemble.py:266`; the arm helper overrides to 900 at build time. The
runner's `RUN_TIMEOUT` reads from `SWEBENCH_RUN_TIMEOUT` (default 1800) at
`scripts/assay_swebench_confirmatory.py`. `run_swebench_one` at
`swebench.py:397` takes a `timeout_seconds` argument. Three numbers, three
lexicons, three defaults. The v3 design's per-cell budget calculation
(topology watchdog + per-repo grade timeout + 5-minute margin) sums them
but does not unify them into a single number visible in the cell row.

`run_swebench_one`'s `timeout_seconds` parameter is the missing primitive
for the grader half; the runner and topology halves still enforce their own
numbers. One per-cell budget applied at one enforcement point remains
unshipped.

### Move 9 — `embedded_substrate` has no consumer (OPEN)

`kernel/composition.py:84` still houses `embedded_substrate` — the
substrate-as-Producer primitive designed to factor a shared sub-topology
across three consumers (`swebench_solver`, `coding_flow`, `code_evolution`).
The round-3 solver design at `docs/swebench/swebench-solver-design.md:82-86` called
this out explicitly: best-of-N + correction loop is duplicated across the
three topologies today; factoring via `embedded_substrate` would give one
contract. No consumer has appeared. This is the largest Substrate-primitive
underuse in the codebase; deferrable, not urgent.

### Move 4 half-open (rename shipped, retirement did not)

Rename made `swebench_solver_topology_with_test_selection` explicit at
every call site. No study of in-topology selection versus harness-only is
scheduled. No deletion sequence, no `_deprecated/` move, no KIT_DIARY
retirement entry. Six days from now the rename will read as normal and a
future refactor will pipe through it again — the postmortem's RC2 pattern
returning through the same door with a longer sign on it.

---

## SDD adherence after the day's landings

Weighted by load-bearing rule, adherence rises from the holistic review's
80 percent to roughly 87 percent. The four v3 halts closed rule 2
(vocabulary evolution), rule 4 (halt-and-articulate), and the observation
contract half of rule 9. Gap 7 from the 2026-08-09 conformance review
closed. Two things newly landed that should be back-propagated:

- The `vocabulary_change_required` halt on `REASON_RATE_LIMITED` this
  morning is exactly the shape AGENTS.md hard rule 2 asks for. BLACKBOARD
  Decisions 2026-08-11 records the ratification. This is the second real
  vocabulary halt this week; the first was H-1 for `Verdict`. Two
  data-points make the discipline routine, not ceremony.
- The observation contract at N=300 catching the throttle failure is
  evidence that hard rule 9's third leg pays rent — a content assertion
  would have said "cells wrote rows"; the observation contract said "the
  wire form matches June 27, or it doesn't." It didn't.

Gaps still open: 1 (Sprint 0 vocab), 2 (deletion policy), 3 (string-literal
canonical home registry), 6 (`CellSource` enum for runner `source` field —
still stringly typed at line 186), plus the two new gaps the holistic
review named (runner bypasses `run_suite`, matrix is code where it should
be data).

---

## What the day proved that no prior review had named

Three things.

**One — the observation contract's second purpose.** H-4 was written to
prove the confirmatory shape holds against June 27's 108/300. It also
proved that a wide-enough gate reveals systemic failures a narrower gate
would hide. The 82 percent throttle rate needed 4000+ requests to become
visible; N=20 would have made it look like model variance. This is
generalizable — every future observation contract should be sized not only
for the primary claim's CI but for the second-order failures the run's
scale exposes.

**Two — the rate-limit shim is a Substrate primitive, not a SWE-bench
one.** `RateLimitedResponder` wraps any `Responder`; `ProviderQuota` types
any provider tier. The shim lives at `substrate/adapters/rate_limit.py`,
not under `assay/`. Every future Substrate topology that talks to a rate-
limited provider gets the same protection. That is the correct home for
this class of code, and the day's execution put it there without asking.
When the next provider lands, the shape is one classmethod per tier per
provider — the interface stays the same. This is exactly the North Star
T5 shape ("small-model orchestration is the horizon") being built quietly
in service of an assay, without any north-star ceremony.

**Three — F8 (`container_arm`) is the North Star's T3 in miniature.** The
North Star claims Substrate strategies are named, factored, invocable by
name. `container_arm(name, role, model)` and `host_arm(name, role, model)`
are two named factored strategies for the SWE-bench arm role, addressable
by name, using different topologies underneath. The pattern the North Star
sketches for `code_review.adversarial` and `code_generation.spec_first`
already ships for `swebench.container` and `swebench.host` — quietly, as
part of the confirmatory work, without the cockpit or the strategy registry
being in place yet. The evidence for the North Star lives in the code
already.

---

## Five moves that would land the rest of the holistic review

1. **Collapse the five parametric arms into one factory + a data table.**
   `swebench_matrix.py` shrinks by ~100 lines. New arms of the same shape
   add a row. This is finding 2, straightforward mechanical work, half a
   sprint.

2. **Fold the runner's generic pieces into `run_suite`.** Identify
   salvage, resume, per-cell wall budget, typed cell rows, batch-grade
   dispatch, tier verification as generic assay concerns. Extend
   `assay/run.py` to carry them; the SWE-bench runner drops to ~200 lines
   of genuinely SWE-bench-specific glue. Two sprints.

3. **Unify the three timeout regimes into one per-cell budget** derived
   from the per-repo grade table, applied at `run_suite`'s per-cell
   `wait_for`, with the topology watchdog and grader timeout both derived
   from it. Visible in every cell row. One sprint.

4. **Retire `swebench_solver_topology_with_test_selection`.** Either move
   it under `topologies/swebench_solver/_deprecated/` with a KIT_DIARY entry
   naming last-live sha and retirement reason, or commit a sprint that
   measures its in-topology selection against harness-only selection on 300
   Lite cases and reports the delta. Alive-for-research without a research
   plan is not neutral — it is a call site waiting to be misused.

5. **Sprint 0 vocabulary session for the SWE-bench sub-topology.**
   Retrofit the nine tags as `signals/0.2.json` with a rationale doc.
   Closes SDD Gap 1. Half a sprint.

Move 9 (`embedded_substrate` factoring the shared best-of-N sub-topology)
stays deferred — a week's work, best done after moves 2 and 3 land, since
extracting the shared shape from three consumers touches every consumer.

---

## The one paragraph

The 2026-08-10 design chain executed cleanly across seven commits, closed
four SDD halts, and shipped the first structurally distinct SWE-bench arm
the North Star had been calling for. The wire-check at N=300 fired and
surfaced an 82 percent provider throttle rate the topology was silently
absorbing — evidence H-4's insistence on N=300 was right, and evidence the
observation contract's second purpose is exposing failures a narrower gate
would hide. Today's rate-limit shim is the correct fix in the correct
place (`substrate/adapters/rate_limit.py`, provider-agnostic, typed
exception, vocabulary halt filed and ratified same day). Six of the nine
holistic-review moves shipped or partially shipped. Five stand open; the
largest, the 837-line bespoke runner bypassing `run_suite`, grew this week
by every landing that added to it. F8 and the rate-limit shim together
prove the North Star's T3 (named strategies) and T5 (provider-agnostic
orchestration) claims already have working code — quietly, in service of a
benchmark, before either theme has its own cockpit or registry. That is
the shape a healthy application takes when the substrate under it is real.

---

*Sources this review cites, in order of appearance:
`git log --oneline` between commit `265e050` (holistic review) and HEAD;
`docs/review/REVIEW-2026-08-10-swebench-holistic.md`;
`docs/DESIGN-2026-08-11-responder-rate-limit-shim.md`;
`src/substrate/assay/swebench_errors.py`;
`src/substrate/adapters/rate_limit.py`;
`src/substrate/assay/swebench_matrix.py`;
`src/substrate/assay/swebench.py`;
`src/substrate/assay/oracle.py`;
`src/substrate/assay/run.py`;
`src/substrate/assay/suite.py`;
`src/substrate/kernel/composition.py`;
`src/substrate/topologies/swebench_solver/assemble.py`;
`scripts/assay_swebench_confirmatory.py`;
`process/BLACKBOARD.md ## Surfaced for review` and `## Decisions`
(2026-08-10 and 2026-08-11 entries);
`docs/NORTH-STAR-2026-08-10-v5.md`;
`docs/swebench/swebench-assay-roadmap.md`;
`sdd-kit-2/AGENTS.md`.*
