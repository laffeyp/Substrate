# PAPER — What went wrong on SWE-bench, and what SDD would have done on day one

> **Status note (Sprint 184, 2026-08-12).** External round-2 review at
> `docs/review/REVIEW-2026-08-12-round2-what-round1-missed.md` § M2 flagged this
> paper as **positioning, not audit**. Three specific reasons: the title
> ("the SDD remedy") imports the adoption framing the standing memory
> `feedback-no-market-framing-correctness-is-the-point` forbids; § 10
> "What NOT to conclude" violates the standing memory
> `feedback-writing-no-negative-examples-banned-schoolroom`; the
> natural-experiment argument in §§ 2 and 7 does not control the variable it
> claims to isolate (see round-2 R1 for the missing behavioral evidence).
> Two additional stale claims sit inside: § 3.1's "dead vocabulary is still
> open" (element_localizer was wired at Aug-8 fold, `assemble.py:501-508`);
> § 3.2's `BaseException`-catch citation (Sprint 169 narrowed it hours before
> the paper landed).
>
> **This document does not have review authority.** It is retained on disk
> per hard rule 12 (no deletions; the audit trail is the work) but is not
> the source of truth any subsequent sprint cites. The technical postmortem
> that carries the divergence record without the positioning framing lives
> at `docs/POSTMORTEM-2026-08-10-swebench-topology-drift.md`; the primitive
> gap analysis lives at
> `docs/review/AUDIT-2026-08-12-substrate-usage-in-swebench-work.md`; the
> sprint chain lives at
> `docs/review/ROADMAP-2026-08-12-swebench-rebuild-sprint-chain-v2.md` (with
> the round-2 R3/R4 corrections applied at Sprint 181). Any doc that
> currently cites this paper as authority should read those instead.
>
> Sprint 184 files this note rather than editing the body because the audit
> trail is the work; the paper's argument stands on its own record even
> when the argument's framing is rejected. A rewrite as technical postmortem
> would be a new dated document, not an in-place edit.

*A reviewer's diagnosis. Not a plan. Not a status. This paper walks the
specific SDD violations that turned one Substrate application into four weeks
of running sores, names the six external boundaries that raise the floor of
difficulty for this benchmark specifically, walks the counterfactual — what
Sprint 0 through Sprint N would have produced — and pressure-tests the claim
that SDD is not optional for LLM-authored programs at this complexity.*

*Author role: reviewer. Deliverable: findings handed to the build side.
Sources: `sdd-kit-2/AGENTS.md`, `sdd-kit-2/foundations/01-04`,
`sdd-kit-2/grammar/PRINCIPLES.md`; `docs/POSTMORTEM-2026-08-10-swebench-topology-drift.md`;
`docs/DESIGN-2026-08-10-swebench-confirmatory-revert.md` (v1, v2, v3);
`docs/review/REVIEW-2026-08-09-sdd-conformance-swebench-additions.md`;
`docs/review/REVIEW-2026-08-09-swebench-runner-shape-and-walltime.md`;
`docs/review/REVIEW-2026-08-10-swebench-confirmatory-revert-v2.md`;
`docs/review/REVIEW-2026-08-10-swebench-holistic.md`;
`docs/review/REVIEW-2026-08-11-swebench-re-review.md`;
`docs/NORTH-STAR-2026-08-10-v5.md`; `docs/swebench-first-principles-2026-08-09.md`;
`docs/swebench-solver-design.md`; `process/BLACKBOARD.md`;
the code cited by every review above at current-HEAD line numbers.*

*Date: 2026-08-12.*

---

## Abstract

The SWE-bench work on this project took four weeks to reach a state every
other topology in the tree reached in one sprint. The reason is not
model quality, not benchmark difficulty, not compute constraints. The reason
is that `sdd-kit-2/AGENTS.md`'s twelve hard rules were followed on every
other application in the tree and skipped on this one. The natural experiment
sits inside the project: `swebench_repair_topology` at
`topologies/swebench_solver/assemble.py:257` — built simple, one artifact,
bounded scope — closed 108 of 300 SWE-bench Lite instances on 2026-06-27
(KIT_DIARY entry 26, commit `0aab945`). `swebench_solver_topology_with_test_selection`
at `assemble.py:438` — built sprint-by-sprint through July and early August
without a Sprint 0 vocabulary session, without a resource budget per
producer_kind, and without a bridge-mapping section for its six external
boundaries — collapsed on 2026-08-09, producing 517 silent-fail cells and a
resolve number that meant three different things depending on which
denominator a reader picked. Same team, same substrate, same models, same
period. The only variable that differed is the discipline. This paper walks
the specific violations, maps each to the failure it produced, specifies
what Sprint 0 through Sprint N would have produced instead, and pressure-tests
the underlying claim: LLM-authored programs at real complexity fail without
external check surfaces, and SDD is the smallest working set of external
check surfaces the field has produced.

---

## Section 1 — The claim

An LLM writing code has no memory of what it decided yesterday, no continuous
model of the codebase's evolution, and no reliable ability to self-correct
its own reasoning. Two recent results anchor the last point.

Huang et al. (2023, *Large Language Models Cannot Self-Correct Reasoning Yet*,
ICLR '24) show intrinsic self-correction degrades reasoning quality on
average. Tyen et al. (2023) show error detection is the bottleneck, not
error fixing — the model can fix a bug it is told about, and fails to detect
the bug in the first place. Both results say the same thing: without external
check surfaces the LLM cannot reliably improve its own output.

SDD-kit-2's discipline is a small closed set of external check surfaces
adapted for LLM authorship. The locked vocabulary (`signals/0.1.json`) is
one such surface — a set-difference between the emitted tags and the
declared tags is mechanical, not opinion. The dual contract (signal +
artifact + observation) is a second — the Architect runs the build; the
tests either pass or they don't. The Rubber Duck Pass narrates the trace in
the vocabulary's own terms; the categories are all set-difference against
the vocabulary or the sprint card, not against the model's own opinion. The
Signal Report is a third — its shape names what the sprint tried to produce,
grading itself against the sprint card the human wrote.

`sdd-kit-2/AGENTS.md` § "Why the pass is defensible" spells this out. The
Rubber Duck Pass works *because* it is grounded in external check surfaces,
not because LLM self-critique is trustworthy. Without those surfaces the
pass degrades into intrinsic self-critique, which the literature above says
is contested at best.

The claim of this paper: at the complexity of a Substrate application with
six external non-deterministic boundaries — LLMs, provider rate limits,
Docker daemon, image registry, GitHub, and an external Python harness
running pytest inside a Docker container — the LLM authoring the code will
produce silent drift, dead vocabulary, retyped literals, and un-defended
boundaries whenever the SDD discipline is not present. The natural
experiment of this project is the evidence.

---

## Section 2 — The natural experiment

The `substrate/` tree contains twelve bundled topologies (per North Star
v5's inventory at
`docs/NORTH-STAR-2026-08-10-v5.md` § "What substrate has that fits"):
`coding_flow`, `code_review`, `code_evolution`, `best_of_n`, `tool_loop`,
`pair_coding`, `natural_conversation`, `debate`, `adversarial_pair`,
`game_of_life`, `intel_asymmetry`, `swebench_solver`. Eleven of the twelve
run clean on their conformance tests and their walkthrough demos. One
does not.

The eleven that work were built to SDD from Sprint 0. Each has a locked
vocabulary; each has a bridge-mapping section in `WORKING_AGREEMENT.md`
naming the external substrates it touches; each producer_kind declares its
schemas and its determinism; each sprint that touched behavior added an
observation contract per hard rule 9.

The one that does not was built starting at sprint 133 without a Sprint 0
vocabulary session for the sub-topology, without a bridge-mapping section
naming the six external boundaries it sits on, and without a resource
budget on the `select_exec` producer_kind that would have caught the
in-topology Docker-load explosion at build time. The gaps are recorded in
`docs/review/REVIEW-2026-08-09-sdd-conformance-swebench-additions.md`
(the 2026-08-09 external conformance pass, weighted 85 percent
adherence — the seven gaps enumerated below are that pass's own numbering).

Same author (this Claude session and the sessions before it). Same substrate
(the kernel, record, projections, adapters, assay layer — all shipped and
proven). Same models (Ollama Cloud through the same `OllamaResponder`).
Same period (June through August 2026). The only variable that differs
between the working eleven and the failing one is the presence or absence
of SDD discipline at Sprint 0.

Two objections to this experiment as evidence:

**"SWE-bench is uniquely hard because of the six boundaries."** True and
insufficient. The six boundaries raise the floor of difficulty; they do not
explain why the ceiling collapsed. `tool_loop_container` (F8, landed
2026-08-11 at commit `2f311d6`, `swebench_matrix.py:110`) is a second
SWE-bench arm that touches the SAME six external boundaries — same
Docker, same image, same pytest, same harness, same LLM. It is a
one-producer topology that emits `SelectedPatch` cleanly, terminates on
`threshold_count("SelectedPatch", 1)`, and lands rows in the wire-check with
a typed verdict. Same boundaries, structurally simpler build, built with the
discipline the holistic review named. It works.

**"Sprint 133 didn't have Sprint 0 to run yet because the SDD kit was still
being refined."** False. SDD-kit-2 shipped at the start of the project. The
coding assay ran a Sprint 0 vocabulary session; the swebench sub-topology
did not. The choice was to inherit substrate's Sprint 0 vocabulary lock and
grow the swebench vocabulary sprint-by-sprint on top of it. That choice is
the gap.

The experiment is what it is. The evidence points where it points.

---

## Section 3 — What specifically went wrong

Every claim below carries a citation. No claim rests on reconstruction.

### 3.1 The vocabulary grew after the resolve rate had been reported

Twelve tags in the swebench sub-topology grew sprint-by-sprint from sprint
133 onward: `SuspectFiles`, `SuspectElements`, `EditLocations`,
`ReproductionTest`, `TestResults`, `AppliedPatch`, `SelectedPatch`,
`RepairSummary`, `Reproduction`, `Solved`, `Draft`, `Candidate`,
`Exhausted`. Three vocabulary halts landed in sprints 147-149 *after* the
108/291 exploratory run had already produced a number. This is Gap 1 of the
2026-08-09 conformance review and it maps precisely to `sdd-kit-2/AGENTS.md`
hard rule 12's soundfield citation: *"soundfield's vocabulary materialized
at sprint 60 of 67; the prior 59 sprints inherited the gap."* The prior 59
sprints of soundfield produced the same shape of drift the swebench
sub-topology produced through July. The gap is still open.

The concrete cost: `SuspectElements` was defined at `records.py:51-55` and
exported at `swebench_solver/__init__.py:37`. No producer emitted it and no
consumer read it for roughly seven weeks. The runtime enforces the schema
at emit — an unknown tag becomes a `ProducerEmittedInvalidEvent`. It has no
symmetric check for a declared tag with no emitter. Nothing said "there is a
tag in the vocabulary that nobody is using." F9 in the 2026-08-08 fold pass
finally wired `element_localizer_factory` in place of `localizer_factory` at
`assemble.py:398`. Seven weeks of dead vocabulary.

### 3.2 The runner bypasses the assay control plane

`scripts/assay_swebench_confirmatory.py` weighs 837 lines. Every other
assay in the tree uses `run_suite` at `assay/run.py:101`, which is 12
lines. The SWE-bench runner reimplements the outer walker with
`asyncio.Semaphore`, per-cell `asyncio.wait_for`, salvage-mode regrade,
checkpointed resume, cell-row writing, batch-grade dispatch, tier
verification, and typed error classification. Every one of these is a
generic assay concern.

Sprint 144a's own docstring at
`docs/swebench-close-the-loop-roadmap.md` § "Group A" enumerates eight
"parity gaps against `bench_coding.py`" — meaning the two runners are
converging by hand-copying. The right primitive was `run_suite`; the shape
that got built was a bespoke script that grows every week. This is Move 3
of the 2026-08-10 holistic review. It has been open for two days and grew,
not shrank, in that time.

The concrete cost: every improvement to `bench_coding.py`'s runner has to
be back-ported to `assay_swebench_confirmatory.py` by hand. When
`bench_coding.py:129` learned to set `UsageTotals.estimated` from the
record, the swebench runner did not. When `bench_coding.py:226-231`
learned to refuse mixed configs on resume, the swebench runner did not.
Sprint 144a's punch list is what running the same discipline in two places
by hand looks like.

### 3.3 The topology grew without a resource budget

`swebench_solver_topology_with_test_selection` at `assemble.py:438` (the
former `swebench_solver_topology`, renamed at commit `3883973` and now
retired) contained the `select_exec` producer_kind at `assemble.py:97-125`.
`_select_exec_factory` fires `asyncio.gather` over every applied candidate
patch, launching `DockerTestRunner.run` per patch. With `n=3` and
`max_rounds=2`, this is up to six concurrent Docker runs per cell inside
the topology. `select_docker.py:153-192` calls `docker run --rm` per
invocation; startup and teardown cost 2-5 seconds per container.

`sdd-kit-2/AGENTS.md`'s twelve rules do not contain a "declare a resource
budget per producer_kind" rule. This is the missing rule.
`docs/POSTMORTEM-2026-08-10-swebench-topology-drift.md` § "Discipline for
prevention" names it: *"Every station has a bounded contract."* The
postmortem then defers the fix to a follow-on kernel change: *"Every
topology stage declares a resource budget. This is a follow-on kernel
change and lands in a separate design doc."* The v3 design at
`docs/DESIGN-2026-08-10-swebench-confirmatory-revert-v3.md` schedules the
change for the next kernel sprint after the confirmatory result lands.

The concrete cost: 1500 cells at up to eight concurrent Docker containers
per cell hangs the Docker daemon on sympy and django repos, produces the 517
silent-fail count on the 2026-08-09 run, and turns 11 wall-clock hours into
three different resolve numbers depending on the denominator a reader picks.

### 3.4 Silence at the harness rolled into `resolved=false`

`assay/swebench.py:305` (the pre-v3 shape) caught `FileNotFoundError` from
`read_resolved` and returned `(resolved=False, detail=...)`. `SwebenchExtractOnlyOracle.grade`
at `swebench.py:515` returned `passed=False` unconditionally as a
placeholder. Both patterns rolled a third grade state — no verdict — into
one of two typed states, `PASS` or `FAIL`. Every harness timeout, container
crash, docker daemon hiccup, and missing report became a visible failure
that looked identical to an honest failed try.

This is `sdd-kit-2/grammar/PRINCIPLES.md`'s Commitment 2 (speaker-side
validation) applied at the wrong seam. The runtime validates emitted events
against the declared schema; it does not validate that the schema itself
covers every state the underlying system produces. The oracle's schema had
two states; the harness produced three. The mismatch was in the vocabulary,
not in the code. A Sprint 0 vocabulary session for the sub-topology would
have named the third state — `NO_VERDICT` — as part of the initial lock.
Instead the third state got named in v3's H-1 halt on 2026-08-10, six weeks
after the sub-topology started emitting.

The concrete cost: the 2026-08-09 Verified pass 1 sweep reported 118 out of
1500 cells resolved as 7.9 percent, 118 out of 854 non-empty patches as
13.8 percent, and 118 out of 337 completed grades as 35 percent. Three
numbers, all reported, all misleading in isolation, all downstream of one
vocabulary gap.

### 3.5 Two lexicons, same closed set

Oracle reasons before v3 were `harness_timeout`, `container_crash`,
`docker_error`, `harness_error:<class>`. Runner `source` closed set was
`run`, `salvage`, `timed_out`, `docker_error`, `git_error`,
`firewall_violation`. `harness_timeout` in one lexicon, `timed_out` in the
other. `container_crash` in one, `docker_error` in the other. Same
underlying event, two names. A reader chasing a `no_verdict` with source
`timed_out` could not pattern-match to the oracle's `harness_timeout`
without a translation table nobody wrote.

`sdd-kit-2/grammar/PRINCIPLES.md` Commitment 1 is "vocabulary is the
contract." Two lexicons for one closed set is exactly the drift the
commitment prevents. The v3 H-3 halt collapsed them at
`assay/swebench.py:76` as `_HARNESS_REASONS`, shared verbatim between
oracle and runner. Six weeks late.

The concrete cost: every review of the runner had to include a mental
translation between the two lexicons. Every typed exception's `reason`
field had to be manually mapped to the corresponding runner string. Every
report reader who wanted to count `timed_out` versus `harness_timeout` had
to know they were the same event.

### 3.6 Stringly-typed cell dispositions

`scripts/assay_swebench_confirmatory.py:186` set `source == "run"`,
`"salvage"`, and (implicitly) `"error"` as bare string literals in the cell
row. `assay/cells.py`'s report layer set-differenced on these strings. F10
in the 2026-08-08 fold hunted the same pattern in `assemble.py`'s view
names — six literals hoisted into six constants (`_VIEW_APPLIED`,
`_VIEW_EDIT_LOCATIONS`, etc.). The runner rows had no equivalent hoist
until yesterday's `CellSource` enum landed at commit `1ded31b`.

This is Gap 6 of the 2026-08-09 conformance review. The memory item at
`feedback-read-the-code-grep-repeated-literals` names the pattern: retyped
kind/status/verdict strings are the drift that green gates (mypy, ruff)
cannot see. `CellSource` closes the gap for this specific string, six weeks
after the pattern was named as a class in F10.

### 3.7 External model tags had no verification gate

`qwen3-coder:480b-cloud` was retired by Ollama Cloud on 2026-07-15. The
Sprint 160 pass-2 fold on 2026-08-09 discovered the retirement live during
a run. Substrate's `verify_constants` at `assay/swebench.py:219-239` gates
the swebench-package SDK constants against the installed package; there was
no symmetric gate for external model tags. Gap 7 of the conformance review.
Yesterday's commit `4fb4eaf` closed it: the runner now pings every declared
model at startup and halts on any dead one.

The concrete cost: a live model retirement took down a run that had been
budgeted for tens of wall-clock hours. Detection at startup would have
halted before the first cell fired.

### 3.8 Deletions violated hard rule 12

Sprint 146 deleted four files: `scripts/assay_full_run.py`,
`scripts/swebench_smoke.py`, `scripts/assay_swebench_smoke.py`,
`scripts/assay_agent_debug.py`. `AGENTS.md` hard rule 12: *"Delete files.
New thinking goes into new files / folders / round-N versions. The audit
trail is the work."* The deletion carve-out was documented in the roadmap
but not promoted to a kit-level ADDENDUM. Gap 2 of the conformance review.
Still open.

The concrete cost: `assay_full_run.py` was the June 27 shape. Deleting it
left no runnable path to the working shape. When the current pass produced
8 percent resolve, no one re-ran the June 27 script to confirm the
regression, because the script no longer existed. The postmortem's CF4 (*"I
did not re-read the git history"*) is downstream of the deletion. A rule 12
retention would have kept the working shape one command away.

---

## Section 4 — The six external boundaries

Every other Substrate application has one external non-deterministic
dependency: the LLM, via `Responder`. `substrate/adapters/models.py` names
the seam. `substrate/reference/_models.py` supplies a `DeterministicResponder`
for CI. `substrate/kernel/topology.py` records every `Responder` call as a
typed `ModelUsage` event on the replayable record. One boundary, one seam,
one gate.

SWE-bench sits on six.

### B1 — LLM via provider (Ollama Cloud)

The `Responder` boundary Substrate was designed for. Defended today by
`OllamaResponder` with retry, timeout, and the `ModelUsage` recording. This
was the boundary that DID work — most of the time.

### B2 — Provider rate limits

Ollama Cloud tiers cap concurrent models: Free 1, Pro 3, Max 10. The
2026-08-10 N=300 wire-check hit this and 82 percent of HTTP calls returned
429 (`docs/DESIGN-2026-08-11-responder-rate-limit-shim.md`). Substrate had
no defense. The shim landed 2026-08-11 at commits `c3cf0c9` and `3170dc3`:
`substrate/adapters/rate_limit.py` wraps any `Responder` with a
per-`(provider, model)` `asyncio.Semaphore` sized to the tier's declared
limit plus honest `Retry-After` handling. Boundary defended.

### B3 — Docker daemon

Container start, container exec, container kill, container reap, image
pull, image storage. `assay/swebench.py:397`'s `run_swebench_one` now owns
the boundary for the grade path with `subprocess.run(..., timeout=T)` +
`docker kill` in the `except subprocess.TimeoutExpired`. The topology's own
Docker calls (through `select_exec`, `select_docker`, `repro_base_validate`)
were retired with the heavy topology at commit `3883973`. The remaining
Docker touches are the grade and the `container_arm`'s solve loop. Both
have per-call ownership; neither has a container-count budget gate.

Partial defense. A daemon-side OOM eviction, an image-pull throttle from
Docker Hub, or a container that segfaults still returns as
`NO_VERDICT` with `reason="container_crashed"` or `"docker_error"` — typed
and honest, but nothing prevents the sweep from continuing into a wedged
daemon. A daemon-health pre-flight (analog to the model pre-flight at
`4fb4eaf`) would close this. Not scheduled.

### B4 — Docker image registry

The swebench eval images live on Docker Hub under
`swebench/sweb.eval.x86_64.<repo>_<version>_<instance_hash>`. An image 404
(instance retired upstream, image missing for a specific version) shows up
as `HarnessError` at grade time. `verify_constants` at
`assay/swebench.py:219-239` gates the swebench-package version; there is no
symmetric gate for the image inventory. A `docker manifest inspect` per
declared instance at run start would close the boundary. Not scheduled.

### B5 — GitHub for repo clones

Bare cloning astropy (~700 MB) 8 times in parallel over one pipe triggered
GitHub's throttle during 2026-08-09 prep. Defended by the mother-clone
cache at commit `8af9866`: one bare clone per repo under
`~/.cache/substrate/swe-mothers/<owner__repo>.git` with `fcntl.flock`
serialization on first miss, then `git clone --local` (hardlinked) per
instance. Boundary defended.

### B6 — The swebench harness itself

The `swebench` Python package's `run_evaluation` subprocess invokes pytest
inside the eval container and writes `report.json`. Version drift (an SDK
rename between 4.0 and 4.1) is caught by `verify_constants`. Harness
raising inside the subprocess is caught by `run_swebench_one`. Harness
hanging (rare) is caught by the wall-clock deadline. Boundary defended.

**Summary.** Two boundaries fully defended (B5, B6). One boundary defended
except for daemon-health pre-flight (B3). One boundary undefended (B4). One
boundary defended this week (B2). One boundary Substrate was built for (B1).
Every defense is a Substrate-level primitive that ships once and applies
everywhere any future application touches that boundary. The rate-limit
shim proves the pattern.

The reason each new wire-check produces a new failure is that a
boundary the current defenses do not cover gets hit for the first time at
the scale the wire-check runs at. There are six boundaries; there were
four undefended at the start of August; there are one and a half
undefended today; the sequence is finite and mechanical. The frustration is
accurate; the shape is not surprising once named.

---

## Section 5 — The June 27 window

Commit `0aab945` on 2026-06-27 produced 108 of 300 SWE-bench Lite instances
resolved. Every attempt since to reproduce the number in the same
neighborhood has surfaced a new failure. The reason is that the environment
under the run has moved:

- **Model retirement.** `qwen3-coder:480b-cloud` was retired 2026-07-15.
  The June 27 run used it. Every subsequent run used a substitute (from
  the ensemble triplet). Boundary B1 changed under the project.
- **Rate limits.** Ollama Cloud Pro's 3-concurrent-model cap was not
  reached at whatever concurrency the June 27 run used. Later runs at
  CONCURRENCY=8 across an ensemble hit it hard. Boundary B2 changed under
  the project.
- **Topology weight.** The heavy topology (`swebench_solver_topology`) did
  not exist on June 27. It was built in sprints 155-159 through July into
  early August. The June 27 shape was `swebench_repair_topology` — three
  stages, no in-topology Docker. Boundary B3's cell-count exploded because
  the topology added a producer_kind that fires up to six Docker containers
  per cell.
- **GitHub bandwidth.** The mother-clone cache did not exist. Parallel bare
  clones of astropy triggered a throttle that took roughly ten minutes to
  produce zero prepared cases. Boundary B5 surfaced.
- **Instance timeouts.** The harness's per-instance 30-minute cap was
  rarer at N=300 Lite than at N=500 Verified. sympy and django hit the cap
  routinely on Verified. Boundary B6 surfaced at the harder split.

The June 27 run is not a code shape you can restore. It is a moment in an
environment that has moved. Every "regression" since is an unguarded
environment change surfacing as a project failure because Substrate had no
gate against the change.

The correct reading of "it worked a week ago" is: the environment permitted
one specific code shape to produce a specific number on a specific split. A
Substrate-level defense against the environment's motion would have kept
the number producible as the environment moved. Those defenses are the six
above. Five of the six are shims or gates or caches that ship once. That is
the work.

---

## Section 6 — What Sprint 0 through Sprint N would have produced

The counterfactual is specific. If SDD had been applied on day one of the
swebench sub-topology, the following artifacts would exist before any
topology code shipped.

### Sprint 0 — Vocabulary session for the sub-topology (one day)

Following `sdd-kit-2/grammar/BOOTSTRAP.md`'s twelve-step procedure, the
Architect + Agent would produce `signals/0.2.json` extending the
substrate-kernel vocabulary with the swebench sub-topology's tags. Every
tag would carry:

- A name (`SuspectFiles`, `SuspectElements`, `EditLocations`, ...).
- A category (LOCALIZE, REPAIR, SELECT, EMIT).
- A payload schema (typed fields, required and optional).
- A vocabulary invariant ("SelectedPatch fires exactly once per case";
  "SuspectFiles precedes any AppliedPatch").
- The dual observable (per rule 25) — for `SuspectFiles`, the
  `recall_at_k` metric against the gold patch's touched files.

Crucially, the session would name the closed set of grade outcomes at the
oracle boundary. The three-state (`PASS`, `FAIL`, `NO_VERDICT`) would be a
Sprint 0 lock, not a v3 halt six weeks later. `NO_VERDICT`'s reason strings
would be a Sprint 0 closed set, not a v2 review finding.

### Sprint 0.5 — Bridge mapping for the six boundaries (half a day)

`WORKING_AGREEMENT.md` would gain a "SWE-bench external substrates" section
naming each of B1-B6, the shape of its non-determinism, the substrate seam
that admits it, and either the shipped defense or a scheduled sprint to
build the defense. Example:

```
B2 — Ollama Cloud rate limits (Free 1, Pro 3, Max 10 concurrent models
per tier).
  Seam: OllamaResponder at adapters/models.py.
  Defense: RateLimitedResponder at adapters/rate_limit.py (scheduled Sprint 3).
  Failure mode: 429/503 storm; typed exception ProviderRateLimited;
  runner catches and records reason=rate_limited on the cell row.
```

Doing this bridge-mapping on day one would have caught the rate-limit
boundary before the wire-check exposed it as an 82 percent throttle. Sprint
3 would have shipped `RateLimitedResponder` in the natural sequence, not
as a same-day fix after a wire-check catastrophe.

### Sprint 1 — Producer_kind resource budget (kernel change, one sprint)

The rule Substrate is missing per the postmortem's own prevention section.
Every `producer_kind` registration would grow a `budget` field:

```python
b.producer_kind(
    "select_exec",
    schemas=[TestResults],
    factory=..., deterministic=False,
    budget=api.Budget(
        docker_containers=(6, "per-case cap"),
        wall_seconds=(600, "per-container cap"),
        model_calls=(0, "no LLM in this stage"),
    ),
)
```

The runtime would enforce the budget: exceeding the cap raises a typed
event on the record, and the cell row records the budget breach as a typed
`source`. The heavy topology's `select_exec` would have been caught at build
time — its cap of 6 containers × 600 wall-seconds × 3 candidates × 2 rounds
totals a per-cell wall of hours. The build would have refused.

`docs/DESIGN-2026-08-10-swebench-confirmatory-revert-v3.md` defers this to
a follow-on kernel change. In the counterfactual it lands in Sprint 1
because Sprint 0.5's bridge mapping named the boundary, and the budget is
the mechanism that enforces the mapping.

### Sprint 2-N — Topology sprints, each with observation contract

Every behavior-touching sprint would open with an observation contract per
hard rule 9: input fixtures (which SWE-bench instance IDs), expected log
substrings, expected runtime signals, expected artifacts. The 108/300 on
2026-06-27 becomes the observation contract's baseline; any subsequent
sprint that produces a different shape halts with `dual_contract_fail`
before the next sprint dispatches.

Under this discipline the 2026-08-09 pass 1's 517 silent-fail count never
happens. The pass's observation contract expects zero unclassified halts
and a `NO_VERDICT` rate under 5 percent. The 517 breach is a halt, not a
run to completion followed by a postmortem.

### Sprint N+1 — Runner using `run_suite`

The confirmatory runner is a thin script around `run_suite`. SWE-bench-specific
concerns (salvage mode, per-cell wall budget from the timeout table, batch
grade opt-in) fold into `assay/run.py` as generic assay helpers or into
named modules the runner imports. The runner's length is roughly 150-250
lines. Sprint 144a does not exist because there is nothing to bring to
parity — one runner, one shape.

### The four-week counterfactual timeline

**Week 1** — Sprint 0 (vocab) + Sprint 0.5 (bridge mapping) + Sprint 1
(producer_kind budget) + first three topology sprints. `signals/0.2.json`
locked; `WORKING_AGREEMENT.md` gains six-boundary section; kernel gains
budget primitive; localize + repair + emit shipped as three ≤2-file
sprints per rule 6. The topology emits `SelectedPatch` on flask-4045 by
end of week.

**Week 2** — Sprint 4 (grader oracle) + Sprint 5 (assay suite adapter) +
Sprint 6 (wire-check on Lite N=300). The wire-check hits the rate-limit
boundary at week 2 instead of week 6. The Sprint 3 defense (already
scheduled from the bridge mapping) ships in flight. The 108/300 lands or a
diagnostic halt fires — either way the sprint closes with a typed outcome.

**Week 3** — Sprint 7 (matrix arms as parametric factory + data table),
Sprint 8 (five arms wire-checked on Lite N=300), Sprint 9 (Verified pass 1
pre-registration frozen).

**Week 4** — Verified pass 1 fires, produces the mechanism claim's
evidence, Sprint 10 folds the observed K into the pre-registration for
pass 2.

Actual timeline: seven weeks (sprints 133-160), four postmortems, three
external reviews, two topology full rewrites, one runner reinventing
`run_suite`, one dead-vocabulary tag carried seven weeks, five design
document versions across three days.

The counterfactual saves three weeks and every one of the four postmortems.

---

## Section 7 — Pressure test

The claim under this paper is strong: SDD is not optional for LLM-authored
programs at this complexity. The strongest counter-arguments follow, each
with a response.

### Counter 1 — Traditional software engineering discipline (tests, types, reviews) also works

**Argument.** Software engineering has been shipping working systems for
sixty years without a vocabulary session or a dual contract. If the
discipline of tests + strict types + code review is present, the LLM
authoring the code produces working programs.

**Response.** At solo-developer complexity for a shallow-external-boundary
system, this is true. `game_of_life` and the coding assay could have shipped
without SDD-kit-2 if the human took the LLM's output and reviewed each
diff. At multi-week complexity across an application with six external
boundaries and an LLM-authored codebase, tests + types + review are
necessary but insufficient. The evidence: mypy and ruff run clean on every
substrate module for the whole four weeks. The green gates saw none of the
gaps enumerated in Section 3. Retyped literal strings do not violate types.
Dead vocabulary does not violate types. A producer_kind without a resource
budget does not violate types. An oracle with two states where the harness
produces three does not violate types. The green gates report nothing wrong
while the topology drifts.

SDD is the traditional discipline extended for LLM authorship: the
vocabulary is what tests + types cannot see; the dual contract is what
code review cannot enforce mechanically; the observation contract is what a
production check cannot substitute for. The extension is small and
mechanical; the extension is what closes the drift.

### Counter 2 — SWE-bench is uniquely hard because of the six boundaries; the SDD violations are secondary

**Argument.** Even with perfect SDD, SWE-bench at six external boundaries
would take weeks. The SDD gaps are a small tax on top of that structural
floor.

**Response.** Partially true, and it strengthens the paper's claim rather
than weakens it. The six boundaries produce a floor. The SDD violations
raise the ceiling. The natural experiment inside the project — the
`container_arm` at commit `2f311d6` — touches the same six boundaries as
the failing solver topology, was built with three days of the holistic
review's discipline, and works. Same floor. Different ceiling. The
difference is the discipline.

Concretely: even if the SDD gaps had been zero, the six boundaries would
still have required six defenses. Each defense is one Substrate-level
primitive, roughly a day of work each. Six days at Sprint 1 pace. With the
gaps, the six defenses landed in a scrambled order across four weeks,
each one triggered by a wire-check catastrophe. Without the gaps, the six
defenses land in the sequence the bridge mapping names, before the
wire-check that would surface each one.

### Counter 3 — This is a Substrate problem, not an SDD problem

**Argument.** Substrate's guarantees stop at the LLM seam. The six external
boundaries past the seam are outside Substrate's design. The SDD kit
cannot be the fix for problems Substrate never claimed to solve.

**Response.** Substrate's guarantees do stop at the LLM seam. SDD's
discipline does not. `sdd-kit-2/grammar/BOOTSTRAP.md`'s Sprint 0 procedure
requires naming external substrates before code is written; the bridge
mapping section in `WORKING_AGREEMENT.md` is exactly the interface between
SDD discipline and non-Substrate boundaries. SDD is what names what Substrate
does not guarantee. The gap in this project is that the bridge mapping was
never written for the swebench sub-topology's six boundaries. If it had
been written on day one, each boundary would have had a named defense
either shipped or scheduled — which is exactly what the counterfactual in
Section 6 walks.

### Counter 4 — The problem is that the wrong benchmark was chosen first

**Argument.** SWE-bench is the wrong first benchmark. HumanEval or MBPP
have one external boundary (pytest, no Docker). Prove the pattern on the
shallow benchmark; bring it to SWE-bench when the six defenses are all
built.

**Response.** True and orthogonal. Choosing a shallower first benchmark
would have compressed the six-boundary work; it would not have changed
whether SDD is required. The natural experiment holds: the shallow coding
assay was built to SDD and works; the SWE-bench sub-topology was not and
does not. The benchmark-choice question is a separate question about
sequencing risk, and it deserves an answer, but it is not the falsifier
for the SDD claim.

### Counter 5 — LLMs will improve and reduce the need for SDD

**Argument.** As LLMs get better at self-critique, error detection, and
long-horizon consistency, the external check surfaces will matter less.
The current state is a snapshot; the trajectory is toward LLMs that need
less structure.

**Response.** Perhaps. The Huang et al. and Tyen et al. results are two
years old; the models measured are two generations behind current
frontier. The claim of this paper is scoped: at the complexity of a
Substrate application at 2026 model capability, SDD is required. If a
future frontier model can maintain the shape of a codebase across four
weeks of edits without an external vocabulary, dual contract, or
observation contract to check against, the claim weakens. Until then, the
natural experiment stands.

### The falsifier

The claim as stated is falsifiable. If a project of comparable complexity
to this one (multi-external-boundary, multi-week, LLM-authored) shipped
working code without SDD discipline, the claim would fail. The soundfield
project is the reverse case — a project of comparable complexity that
tried without full SDD discipline and produced 60+ sprints of drift. The
prompt-factory v1→v1.2 trajectory is a second reverse case — summary-induced
drift across three versions.

The claim survives its falsifiers so far. Continued survival is a matter of
each new project's evidence.

---

## Section 8 — The generalizable rule for future assays

Any assay whose target is a multi-boundary external system faces the shape
this paper walks. Two rules for the class:

**Rule A — Sprint 0 vocabulary session for every sub-topology.** Not just
substrate's Sprint 0 for the kernel. Every application that adds tags to
the vocabulary runs its own Sprint 0 before any code ships. The session
locks the closed set of grade outcomes at the oracle boundary, the
categories the sub-topology's tags belong to, the vocabulary invariants,
and the dual observable per rule 25. `signals/0.N.json` extends the
kernel's vocabulary; the extension is versioned and signed off in
`## Decisions` before Sprint 1 dispatches.

**Rule B — Bridge mapping for every external non-deterministic
boundary.** `WORKING_AGREEMENT.md` names every external substrate the
application touches, the shape of each substrate's non-determinism, the
seam that admits it, and either the shipped defense or a scheduled sprint
to build the defense. A wire-check that surfaces a boundary the bridge
mapping did not name is a documentation failure, not a code failure — the
fix is to add the boundary to the mapping AND ship the defense.

These two rules together would have compressed the swebench sub-topology's
work from seven weeks to four. Every future assay of an external-grader
system inherits them.

---

## Section 9 — Recommendations for this project

Ranked. The build side owns sequencing.

**R1 — Run the retroactive Sprint 0 for the SWE-bench sub-topology.**
Half a day. Produces `signals/0.2.json` locking the twelve tags that grew
sprint-by-sprint. Rationale doc names every tag added between sprint 133
and today. Closes Gap 1 of the 2026-08-09 conformance review.

**R2 — Write the bridge mapping section for B1-B6.** One hour. Extends
`WORKING_AGREEMENT.md` with the six boundaries, current defense state,
and scheduled sprint for each unshipped defense. Produces a checklist
future wire-checks measure against.

**R3 — Land the `producer_kind` resource budget primitive.** One kernel
sprint. Every producer_kind declares `docker_containers`, `wall_seconds`,
`model_calls` caps; runtime enforces at build time and at run time.
Retires the postmortem's "declare a resource budget" rule from
aspirational to enforced.

**R4 — Fold `assay_swebench_confirmatory.py`'s generic pieces into
`assay/run.py`.** Two sprints. The runner drops from 837 lines to ~200
lines of SWE-bench-specific glue. `bench_coding.py` and the SWE-bench
runner share one outer loop; parity divergence stops.

**R5 — Unify the three timeout regimes** into one per-cell budget derived
from the per-repo grade table, enforced at one point, visible in every cell
row. One sprint.

**R6 — Land the daemon-health pre-flight and the image-registry
manifest check.** B3 and B4 defenses. Half a sprint each.

**R7 — Delete `SwebenchExtractOnlyOracle` and `batch_grade_from_records`
under the light topology.** Ten minutes. Move 8's finish.

None of these are surprises. All were named in prior reviews. R1 and R2
are the ones the natural experiment in this paper argues most strongly
for.

---

## Section 10 — What NOT to conclude

**Do not retire SWE-bench as a benchmark.** The benchmark has economic
weight in the field. The North Star claims Substrate proves an assay
pattern that generalizes to any external-grader system. SWE-bench is one
such system; abandoning it would forfeit the strongest public
demonstration of the pattern.

**Do not blame the benchmark's design.** SWE-bench's shape is
genuinely narrow. The narrowness is not the reason this took four weeks.
The reason is the SDD violations in Section 3.

**Do not blame the models.** The models used through the four weeks were
capable of writing the code that eventually landed. They wrote the code.
The problem is what happened between the code they wrote and the shape
the system settled into over multiple sprints.

**Do not blame the team.** The same team built eleven working topologies
in the same period. The natural experiment's independent variable is
discipline, not skill.

**Do not conclude Substrate needs redesign.** Substrate is working. The
kernel, record, projections, adapters, assay layer, and eleven of twelve
topologies are proof. The twelfth is proof of what happens when the
substrate's own guiding discipline (SDD-kit-2) is skipped on one
application.

---

## Section 11 — The load-bearing sentence

This project is the natural experiment. Every application built to SDD
works; the one application not built to SDD is the one that took four
weeks and produced four postmortems. Same team, same substrate, same
period, same models. The independent variable is the discipline. The
soundfield project is the reverse case at larger scale; the prompt-factory
v1→v1.2 trajectory is the reverse case at smaller scale. Every case the
field has produced points the same direction. SDD is not a preference or a
style; it is the smallest working set of external check surfaces the field
has produced for the class of problem that is *LLM authoring a real
program across multiple weeks*. In the absence of those surfaces, the LLM
cannot reliably detect its own drift, and the code accretes toward the
same failure shape every time.

The remedy is what the SDD conformance review named on 2026-08-09 and what
the postmortem's own CF1-CF4 named on 2026-08-10. Nothing new. Applying it
compresses the six-boundary floor to the six-day work it should be, and
turns the wire-check from a catastrophe generator into an accuracy check.

---

*Sources this paper cites, in the order they appear: `sdd-kit-2/AGENTS.md`;
`sdd-kit-2/foundations/01-signal-driven-development.md` through
`04-sdd-claude-design.md`; `sdd-kit-2/grammar/PRINCIPLES.md`;
`sdd-kit-2/grammar/BOOTSTRAP.md`; `docs/POSTMORTEM-2026-08-10-swebench-topology-drift.md`;
`docs/DESIGN-2026-08-10-swebench-confirmatory-revert.md` (v1, v2, v3);
`docs/DESIGN-2026-08-11-responder-rate-limit-shim.md`;
`docs/review/REVIEW-2026-08-09-sdd-conformance-swebench-additions.md`;
`docs/review/REVIEW-2026-08-09-swebench-runner-shape-and-walltime.md`;
`docs/review/REVIEW-2026-08-10-swebench-confirmatory-revert-v2.md`;
`docs/review/REVIEW-2026-08-10-swebench-holistic.md`;
`docs/review/REVIEW-2026-08-11-swebench-re-review.md`;
`docs/NORTH-STAR-2026-08-10-v5.md`;
`docs/swebench-first-principles-2026-08-09.md`;
`docs/swebench-solver-design.md`;
`docs/swebench-close-the-loop-roadmap.md`;
`docs/swebench-assay-roadmap.md`;
`process/BLACKBOARD.md`;
`process/KIT_DIARY.md` (entry 26, entry 37, entry 39);
`src/substrate/topologies/swebench_solver/assemble.py`;
`src/substrate/assay/swebench.py`;
`src/substrate/assay/swebench_matrix.py`;
`src/substrate/assay/oracle.py`;
`src/substrate/assay/run.py`;
`src/substrate/adapters/rate_limit.py`;
`src/substrate/adapters/models.py`;
`scripts/assay_swebench_confirmatory.py`;
`scripts/bench_coding.py`;
external: Huang et al. 2023 (arxiv 2310.01798),
Tyen et al. 2023 (arxiv 2311.08516),
Xia & Chen 2025 (arxiv 2503.15223),
Aleithan et al. 2024 (arxiv 2410.06992),
Kapoor & Narayanan 2024 (arxiv 2407.01502),
Tango 1998, Nam 1997.*
