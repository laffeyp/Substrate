# swebench_solver — locked record vocabulary (sprint 133, the vocabulary session)

**Status: RATIFIED — v0.2 (2026-08-12).** v0.1 locked at Sprint 133 close (2026-06-27, review gate #1
confirmed); the header carried "PROPOSED" past ratification by convention lag, corrected here at v0.2.
v0.2 adds the two vocabulary evolutions that landed via `vocabulary_change_required` halts on 2026-08-10
and 2026-08-11 but were not back-propagated into this doc — the `Result.Verdict` enum (H-1) and the
`_HARNESS_REASONS` closed set (H-3, extended with `rate_limited` on 2026-08-11). Additions live in
§ E below; the v0.1 lock in §§ A–D is byte-preserved. See `process/BLACKBOARD.md ## Decisions` for the
per-halt ratifications and Sprint 161's card for the consolidation work.

Designed BEFORE code (#1). The topology records are frozen msgspec Structs (topology-local, like
coding_flow's), registered in `process/WORKING_AGREEMENT.md`; this doc locks their fields, the #25
dual-contract audit, the shared-sub-topology reconciliation (review #57), and (v0.2) the general assay
Result closed sets that the SWE-bench oracle raises. Strict validator-extras (project posture).

Design: `docs/swebench-solver-design.md`. Vanilla non-agentic solver: LOCALIZE -> REPAIR -> SELECT.

## A. The SHARED best-of-N + correction contract (reused, NOT re-rolled — review #57, finding 12)

Decision: **reuse coding_flow's existing records as the canonical 3-consumer contract** for the best-of-N
+ correction sub-topology. coding_flow, the swebench Repairer (sprint 5), and code_evolution all consume
ONE set; the sub-topology is extracted in sprint 4 (Wave-0 #15). No new shared records are authored — the
reconciliation is "reuse-as-canonical," and these rows are locked in WORKING_AGREEMENT so the three
consumers cannot diverge (#22).

| Record | Locked fields | Meaning |
|---|---|---|
| `Draft` | `round:int, slot:int, context:str` | request to draft candidate `slot` in `round`; `context`="" (seed) or the prior round's deterministic failures (correction). |
| `Candidate` | `round:int, slot:int, response:str` | the model's raw output. coding_flow: `# path:`-headed files. swebench: SEARCH/REPLACE blocks. |
| `Verdict` | `round:int, slot:int, passed:bool, returncode:int, summary:str, source:str="gate"` | the validation of one candidate. coding_flow: the gate. swebench: the APPLIER result (`passed`=applied cleanly + git-diffs non-empty; `summary`=the structured reject reason fed to the next round). `source` (ADDED 2026-08-03, review C-5, additive with a `"gate"` default so the three consumers are unchanged) names WHAT judged: `"gate"` (real process exit in `returncode`) / `"check"` (deterministic predicate) / `"model"` (independent judge — `returncode` is a 0/1 proxy). |
| `Solved` | `round:int, slot:int` | the loop's success terminal (≥1 candidate passed the loop's validation). |
| `Exhausted` | `rounds:int` | every round failed the loop's validation and the budget is spent. |
| `ModelUsage` | (from `reference._models`) | per drafter call, metered onto the record (#3 metering). |

The terminal policy (coding_flow STOPS at the first passing candidate; swebench wants ALL that apply to
flow to SELECT) is a **parameter of the nested topology**, set per consumer in sprint 4 — NOT a record
change. The records above are frozen as written; this is what makes the contract lockable now.

## B. swebench-solver-specific records (wrap the shared loop)

LOCALIZE (before the loop):

| Record | Locked fields | Meaning | Category / stratum |
|---|---|---|---|
| `SuspectFiles` | `files:list[str]` | file-level localization output (LLM-on-repo-skeleton). | localize / event |
| `SuspectElements` | `file:str, elements:list[str]` | class/function localization within a suspect file. | localize / event |
| `EditLocations` | `targets:list[str]` | fine-grained edit targets (`file::element` or `file:line-range`) — the REPAIR loop's input. | localize / event |

REPAIR handoff (the deterministic apply output the shared loop produces for swebench):

| Record | Locked fields | Meaning | Category / stratum |
|---|---|---|---|
| `AppliedPatch` | `round:int, slot:int, model_patch:str, creates_file:bool` | a candidate that applied cleanly, carrying its `git diff` (`model_patch`) and whether it created a new file (the empty-SEARCH path, §4b). The REPAIR->SELECT bridge. `round` completes the lineage (which round produced the winner) for replay/debug provenance. | repair / event |

SELECT (after the loop):

| Record | Locked fields | Meaning | Category / stratum |
|---|---|---|---|
| `TestResults` | `slot:int, regression_passed:bool, reproduction:Reproduction, summary:str` | the solver's own validation of one applied patch: repo-derived regression result + reproduction-test status. **`replayable=False`** — a run-and-observe Docker seam (§4), captured once. `Reproduction` is a typed 3-state enum (`REPRODUCED`/`RESOLVED`/`OTHER`) — enforced at the speaker's mouth (#2 poka-yoke), not by string convention. | select / incident-or-event |
| `SelectedPatch` | `slot:int, model_patch:str, reason:str` | the final submitted patch + why it won (majority vote / regression / reproduction). The topology's output to the swebench oracle. | select / summary |

TERMINAL OUTCOME (the always-emit summary — technique #51; added for `swebench_repair_topology`):

| Record | Locked fields | Meaning | Category / stratum |
|---|---|---|---|
| `RepairOutcome` | enum: `SELECTED` / `NO_LOCALIZATION` / `NO_APPLICABLE_EDIT` | the ENUMERATED terminal states (#53) — why a run produced no patch instead of leaving it implicit in the absence of other events. The judge only declares success when a candidate APPLIES, so the no-patch case splits by whether localization happened. Enforced at the speaker's mouth (#2), like `Reproduction`. | outcome / enum |
| `RepairSummary` | `outcome:RepairOutcome, localized:int, drafted:int, applied:int, selected_slot:int` | the terminal summary (#51): the enumerated `outcome` + the per-stage counts, so a reader learns WHAT HAPPENED from ONE typed event, not by reconstructing it. Emitted exactly ONCE on every `Solved`/`Exhausted` terminal (`swebench_repair_topology` terminates on it); the WATCHDOG terminal emits NONE (a producer speaks only when triggered) and that absence is the runner's `timed_out` signal. `selected_slot` = the chosen slot, or `-1`. NB: `timed_out`/`error` are the RUNNER-level complement to `RepairOutcome` — the terminal taxonomy is complete across the two levels (#53). | outcome / summary |

## C. #25 dual-contract audit — every behavior record has a record-observable

Per the project's record-as-view-side override: each behavior record pairs with a record-observable
assertion (replay L1/L2), NEVER a stochastic-quality claim (review #56). Observation contracts assert
these (#24/#38), flask-4045 seeded.

| Behavior record | Record-observable (what an `assert_event` checks) |
|---|---|
| `SuspectFiles` | emitted once per instance; **recall@k computed + recorded** vs the gold-patch files (==1.0 on the flask-4045 fixture). |
| `SuspectElements`, `EditLocations` | emitted after SuspectFiles; element/location-recall recorded; targets ⊆ suspect files. |
| `Candidate` | one per `Draft` slot; paired with a `ModelUsage` and exactly one `Verdict`. |
| `Verdict` | deterministic given `Candidate.response` — the APPLIER is a pure unit test: gold-matching -> `passed=True` + a non-empty `AppliedPatch`; zero/multi-match -> `passed=False` typed reject (not a crash); overlap -> reject. |
| `AppliedPatch` | `model_patch` git-applies to the base_commit clone; `creates_file` true iff an empty-SEARCH block. |
| `TestResults` | `replayable=False`; the regression set is repo-DERIVED (NOT the `PASS_TO_PASS` field — §4); the allowlist excludes `test_patch` files. |
| `SelectedPatch` | deterministic GIVEN the recorded `TestResults` (best-status pick; regression-only fallback fires when no candidate passes reproduction); IS the submitted `model_patch`. |
| `Solved` / `Exhausted` | the loop terminal; reuses coding_flow's proven observation. |
| `RepairSummary` | emitted exactly ONCE on every `Solved`/`Exhausted` terminal (NOT the watchdog terminal — that absence is the runner's `timed_out`); `outcome==SELECTED` iff a `SelectedPatch` was emitted (chained after it); on `Exhausted`, `outcome` is `NO_LOCALIZATION` iff `localized==0` else `NO_APPLICABLE_EDIT` (a complete partition — Exhausted ⟹ `applied==0`, since the judge Solves on any applied candidate). `applied`==#AppliedPatch; `drafted` is counted from the verdicts buffer and ==#Candidate by the one-verdict-per-candidate invariant (#62/#63). Observation contract: the three outcomes are seeded in `test_swebench_solver.py`. |
| `ModelUsage` | metering, not behavior — no behavior-observable required; one per drafter call (LOCALIZE / each REPAIR candidate / SELECT), summed for the matched-compute axis (#3). |

## D. Open items for later sprints (named, not deferred-silently)

- The shared loop's terminal/collect-vs-stop policy — sprint 4 (extraction), a topology parameter.
- The in-container SELECT test-execution is a NEW bridge (#32/#46) — its bridge mapping is sprint 6,
  distinct from the grade-harness mapping in `docs/swebench-bridge-mapping.md`.
- `EditTarget` as a typed Struct vs the `list[str]` shorthand — `list[str]` for v1 (minimal-complete #6);
  promote to a Struct only if a downstream consumer needs structured fields.
- Sprint 5 (the Repairer): swebench packs spec + edit-targets (from the `EditLocations` view) + prior
  failures into the shared `Draft.context` opaque str — the flex point that makes the reuse work. The
  Repairer's input_builder composes `EditLocations` into `Draft.context`; not a vocabulary gap (review #58).
- Matched-compute forward note (assay-arm stage): the shared loop's short-circuit-on-first-pass (coding_flow)
  vs run-all-N (swebench) parameter has a COMPUTE consequence at equal N — hold the short-circuit policy
  CONSTANT in any coding_flow-vs-swebench compute comparison (review #58).

## E. v0.2 additions (ratified 2026-08-10 / 2026-08-11)

Two closed-set vocabulary additions at the general assay boundary. Their motivating use-case is this
sub-topology; their home is `src/substrate/assay/oracle.py` and `src/substrate/assay/swebench.py`
because both apply to every external-grader oracle, not only SWE-bench. Each landed as a
`vocabulary_change_required` halt under AGENTS.md hard rule 2 and was ratified in
`process/BLACKBOARD.md ## Decisions` on the date shown. This section consolidates them into the
sub-topology's locked vocabulary so a reader of this doc sees the full contract in one place.

### E.1 `Result.Verdict` enum — three-state grade outcome (H-1 + H-2, ratified 2026-08-10)

The general `assay.oracle.Result` gains a `verdict: Verdict` field. Values:

| Value | Wire string | Meaning (SWE-bench specialization in italics) |
|---|---|---|
| `PASS` | `pass` | The graded run produced a definitive positive verdict. *Harness `report.json` exists with `resolved: true`.* |
| `FAIL` | `fail` | The graded run produced a definitive negative verdict. *Harness `report.json` exists with `resolved: false`.* |
| `NO_VERDICT` | `no_verdict` | The graded run completed with no reliable answer (harness timeout, container crash, docker error, harness exception, provider rate limit). Reason string in `Result.reason` from the § E.2 closed set. |

Names are `PASS`/`FAIL` not `RESOLVED`/`NOT_RESOLVED` — `Result` is the general assay contract; the
enum reads correctly for coding assays, replay assays, and any future oracle class. `Result.passed`
became a `@property` returning `self.verdict is Verdict.PASS` under H-2, same ratification — one
field, one fact; no invariant maintained by convention across two fields.

**Rationale.** Pre-H-1 the two-state `passed: bool` rolled harness silence into `passed=False`; the
2026-08-09 Verified pass 1 produced 517 silent-fail cells that were actually `NO_VERDICT`. Enum closes
the gap at the vocabulary layer. Sources:
`docs/POSTMORTEM-2026-08-10-swebench-topology-drift.md` § RC3;
`docs/DESIGN-2026-08-10-swebench-confirmatory-revert-v3.md` § "The oracle contract";
`src/substrate/assay/oracle.py:36-105`.

### E.2 `_HARNESS_REASONS` closed set — `NO_VERDICT` reason strings (H-3, ratified 2026-08-10; extended 2026-08-11)

Every `Result.verdict == NO_VERDICT` carries exactly one `Result.reason` string from the closed set
below. The confirmatory runner's cell-row `reason` field draws from the same set. `Result.reason` is
a first-class field on the general `Result` (promoted to a field at `oracle.py:93` on 2026-08-10 after
N=300 caught the shape leak — earlier readers were parsing it back out of `detail`). One vocabulary;
one translation table; no parsing at the read site.

| Wire string | Meaning | Constant | Typed exception |
|---|---|---|---|
| `timed_out` | Cell exhausted its wall-clock budget. Harness or topology took longer than the per-cell timeout allowed. | `assay/swebench.py:REASON_TIMED_OUT` | `swebench_errors.HarnessTimeout` |
| `container_crashed` | Grade container exited non-zero before `report.json` landed. | `assay/swebench.py:REASON_CONTAINER_CRASHED` | `swebench_errors.ContainerCrashed` |
| `docker_error` | Docker CLI or daemon failure (pull failed, daemon down, OOM eviction, container start refused). | `assay/swebench.py:REASON_DOCKER_ERROR` | `swebench_errors.DockerDaemonError` |
| `harness_error` | Harness raised (import failure, missing image, unexpected exception inside `run_evaluation`). | `assay/swebench.py:REASON_HARNESS_ERROR` | `swebench_errors.HarnessError` |
| `git_error` | `git clone`, `git apply`, or `git checkout` failed at the runner boundary. | `assay/swebench.py:REASON_GIT_ERROR` | `swebench_errors.GitOperationFailed` |
| `firewall_violation` | Instance failed `firewall_check` at admission. Data-bug signal on Verified; downgraded to flake on 2026-08-09. | `assay/swebench.py:REASON_FIREWALL_VIOLATION` | `assay/swebench.py:FirewallViolation` |
| `rate_limited` | Provider (Ollama tier, OpenAI RPM, Anthropic TPM, ...) rate-limited the request; retries exhausted. Extended into the set 2026-08-11 (H-3-ext). | `assay/swebench.py:REASON_RATE_LIMITED` | `adapters/rate_limit.py:ProviderRateLimited` |

`PASS`/`FAIL` verdicts carry `reason == ""` (empty). The frozenset lives at
`src/substrate/assay/swebench.py:_HARNESS_REASONS`; every writer imports the named constant, not the
raw literal — the closed set is checked at the writer boundary.

Adding a reason means: file a `vocabulary_change_required` halt to `## Surfaced for review`, ratify in
`## Decisions`, add the constant to `assay/swebench.py`, add the entry to the `_HARNESS_REASONS`
frozenset, add or extend the typed exception class in `assay/swebench_errors.py` (or a Substrate-level
adapter for provider-agnostic reasons like `rate_limited`), extend this table.

**Rationale.** Pre-H-3 the oracle and the runner ran two divergent lexicons (`harness_timeout` vs
`timed_out`; `container_crash` vs `docker_error`). A reader chasing a `no_verdict` with runner-side
source `timed_out` could not pattern-match to the oracle's `harness_timeout` without a translation
table nobody wrote. Sources:
`docs/DESIGN-2026-08-10-swebench-confirmatory-revert-v3.md` § "H-3 — one closed set of failure-reason
strings"; `docs/DESIGN-2026-08-11-responder-rate-limit-shim.md` § "Closed-set additions";
`src/substrate/assay/swebench.py:55-85`; `src/substrate/assay/swebench_errors.py`.

## G. v0.3 additions — boundary event tags (PROPOSED 2026-08-12, awaiting ratification)

Six new tag families at the general assay boundary layer, each mapping to one substrate producer scheduled in roadmap v2 (`docs/review/ROADMAP-2026-08-12-swebench-rebuild-sprint-chain-v2.md`) at Sprints 5.2 through 5.6 plus S6. The producers land on `src/substrate/adapters/` (Substrate-level, reusable across assays); the events land on the record. Every event follows the `substrate.*` reserved-namespace discipline (Producer-declared kinds MUST NOT collide) but lives under an assay-owned namespace since these are application producers, not runtime primitives. Bridge mapping in `WORKING_AGREEMENT.md` § "SWE-bench external substrates" names each producer's boundary; this section names the tags each producer emits and the invariants over them.

Payload shapes use the same discipline as v0.1 § A–B — primitive types, foreign-key references to `_HARNESS_REASONS` on failure paths, `wall_ms` as an `int` for per-event latency. `t` sits on the envelope; ordering is by `seq`.

**Type conventions in § G.** Two symbolic types recur across the § G payloads and stand for typed contracts rather than bare `str`:

- `Verdict` — the enum from § E.1 (`PASS | FAIL | NO_VERDICT`). msgspec-shaped payload field type; enforced at emit against the enum's `.value` set. Amendment vs the original v0.3 proposal (Sprint 165 fold of external review F5, 2026-08-12): every `verdict` field in § G is `Verdict`, not `str`, so a typo like `"passed"` or `"PASS"` fails at emit rather than reaching the reader.
- `Reason` — a `str` constrained to the § E.2 closed set (`_HARNESS_REASONS`). Represented in the wire as one of the seven `REASON_*` constants at `assay/swebench.py:62-84` or the empty string when `verdict ∈ {PASS, FAIL}`. Enforced at emit by the producer's `assert reason in _HARNESS_REASONS or reason == ""`. Notationally distinct from bare `str` in the payload tables so a reader sees the closed-set discipline at a glance. Not itself an enum — the wire form is a bare `str` for backward compatibility with the ratified `Result.reason: str` at `oracle.py:93`; the constraint lives at the emit boundary.

### G.1 RateLimitProducer events (B2, roadmap S5.2)

Producer wraps any `Responder`, gating the inner call on a per-`(provider, model)` `asyncio.Semaphore` and honoring `Retry-After` on 429/503. Semaphore held only around the in-flight inner call — the retry sleep releases the slot. Terminal exception is `ProviderRateLimited` at `adapters/rate_limit.py`; the exception's `reason` attribute is `rate_limited`.

| Tag | Payload | Stratum |
|---|---|---|
| `RateLimitAttempted` | `provider: str, model: str, attempt_n: int, semaphore_waiters: int` | event |
| `RateLimitGranted` | `provider: str, model: str, attempt_n: int, wait_ms: int` | event |
| `RateLimitDenied` | `provider: str, model: str, attempt_n: int, http_status: int, retry_after_ms: int \| null` | incident |
| `RateLimitRetried` | `provider: str, model: str, attempt_n: int, backoff_ms: int` | event |

**Invariants.** Every `RateLimitAttempted` is followed within the same producer instance by exactly one of: (a) a `RateLimitGranted` (slot acquired, inner call proceeds); (b) a chain of one-or-more `RateLimitDenied` + `RateLimitRetried` pairs ending in `RateLimitGranted`; (c) a chain of `RateLimitDenied` + `RateLimitRetried` pairs terminating in a final `RateLimitDenied` without a following `RateLimitRetried` (retries exhausted; the producer raises `ProviderRateLimited`). Every `RateLimitDenied` carries `http_status ∈ {429, 503}`; every `RateLimitRetried.backoff_ms` is `max(retry_after_ms, exponential_fallback_ms)` from the preceding `RateLimitDenied`.

**Rationale.** The 2026-08-12 N=300 Pro run collapsed because the pre-producer `RateLimitedResponder` shim held its semaphore around the entire retry loop. Under sustained 429 the sleeping workers pinned every slot; throughput collapsed to `capacity / sleep_multiplier`. The producer moves the retry logic into typed events on the record and releases the semaphore during sleeps — the N=30 wire-check missed this because the burst quota absorbed 8 × 503s before the pileup shape could form. Sources: `docs/DESIGN-2026-08-11-responder-rate-limit-shim.md` § "Two things the shim must do"; `process/BLACKBOARD.md ## Surfaced for review` 2026-08-12 halt.

### G.2 ContainerProducer events (B3, roadmap S5.3)

Producer owns one Docker container's lifecycle end-to-end. Spawns via `subprocess.run(..., timeout=T)`; on `TimeoutExpired` calls `docker kill <container_name>` and yields `ContainerKilled`. Container names use the pattern `substrate-<purpose>-<cell_id>-<ulid>` so `docker ps` shows what run owns what container.

| Tag | Payload | Stratum |
|---|---|---|
| `ContainerRequested` | `container_name: str, image: str, cmd: tuple[str, ...], timeout_s: float` | event |
| `ContainerStarted` | `container_name: str, image: str, pid: int, wait_ms: int` | event |
| `ContainerExited` | `container_name: str, exit_code: int, wall_ms: int, stdout_tail: str, stderr_tail: str` | event |
| `ContainerKilled` | `container_name: str, reason: str, wall_ms: int` | incident |

**Invariants.** Every `ContainerRequested` is followed within the same producer instance by exactly one `ContainerStarted`, then exactly one of `ContainerExited` (normal termination, `exit_code == 0`) or `ContainerExited` with non-zero `exit_code` (container-side crash, maps to `container_crashed`) or `ContainerKilled` (wall-clock exceeded, `reason == "timed_out"`). A `ContainerStarted` with no follow-up event on the record is a bug. `stdout_tail` and `stderr_tail` are the last 400 bytes each. `wall_ms` on the terminal event is the elapsed time from `ContainerStarted` to termination.

**No orphaned containers.** After a `ContainerProducer` instance terminates, `docker ps --filter name=<container_name>` returns empty. Enforced by a substance test at `tests/test_docker_producer.py`.

### G.3 ImageProducer events (B4, roadmap S5.4)

Producer resolves and pulls an image before any `ContainerProducer` uses it. Runner pre-flight uses this producer to verify every declared instance image at run start; missing images halt the sweep with typed events on the record before the first cell fires.

| Tag | Payload | Stratum |
|---|---|---|
| `ImageRequested` | `image: str` | event |
| `ImagePulled` | `image: str, digest: str, wall_ms: int` | event |
| `ImageMissing` | `image: str, http_status: int` | incident |

**Invariants.** Every `ImageRequested` is followed by exactly one of `ImagePulled` (cache hit or successful pull) or `ImageMissing` (registry returned 404 or similar). `digest` is `sha256:<64-hex>` from `docker manifest inspect`. `ImageMissing.http_status` distinguishes 404 (image absent) from 5xx (registry error).

### G.4 RepoCloneProducer events (B5, roadmap S5.5)

Producer wraps the existing `_mother_clone` cache at `swebench_suite.py`. Cache-hit path emits `RepoCloneCached`; cache-miss path emits `RepoCloned` after fetching from GitHub. Existing `fcntl.flock` serialization on first-miss survives unchanged.

| Tag | Payload | Stratum |
|---|---|---|
| `RepoCloneRequested` | `repo: str, base_commit: str` | event |
| `RepoCloneCached` | `repo: str, base_commit: str, mother_path: str, checkout_path: str, wall_ms: int` | event |
| `RepoCloned` | `repo: str, base_commit: str, mother_path: str, checkout_path: str, fetch_ms: int, wall_ms: int` | event |
| `RepoCloneFailed` | `repo: str, base_commit: str, error: str` | incident |

**Invariants.** Every `RepoCloneRequested` is followed by exactly one of `RepoCloneCached` (mother clone existed; `git clone --local` hardlinked), `RepoCloned` (mother clone fetched from GitHub, then hardlinked; `fetch_ms` is the bare-clone time, `wall_ms` includes hardlink checkout), or `RepoCloneFailed` (network error, permission error, missing commit). `repo` uses the `<owner>/<name>` shape; `checkout_path` is under `/tmp/assay-swe-<random>`.

### G.5 HarnessProducer events (B6, roadmap S5.6)

Producer wraps the swebench harness subprocess call for one instance. Embeds a `ContainerProducer` internally — the harness call is a container run plus a `report.json` read. Terminal event carries the mapped `Verdict` and the reason string from `_HARNESS_REASONS`.

| Tag | Payload | Stratum |
|---|---|---|
| `HarnessCallFired` | `instance_id: str, image: str, patch_bytes: int, timeout_s: float` | event |
| `HarnessReportRead` | `instance_id: str, report_path: str, resolved: bool` | event |
| `HarnessCompleted` | `instance_id: str, verdict: Verdict, reason: Reason, wall_ms: int` | event |
| `HarnessTimeout` | `instance_id: str, deadline_s: float, wall_ms: int` | incident |
| `HarnessError` | `instance_id: str, error_class: str, wall_ms: int` | incident |

**Invariants.** Every `HarnessCallFired` is followed by exactly one of `HarnessCompleted` (normal grade — `verdict ∈ {Verdict.PASS, Verdict.FAIL}`, `reason == ""`), `HarnessTimeout` (wall-clock exceeded — the terminal's corresponding `GradeResult` from § G.6 carries `verdict == Verdict.NO_VERDICT`, `reason == REASON_TIMED_OUT`), or `HarnessError` (harness raised — the corresponding `GradeResult` carries `verdict == Verdict.NO_VERDICT`, `reason == REASON_HARNESS_ERROR` or `REASON_CONTAINER_CRASHED` per the embedded `ContainerProducer`'s terminal). `HarnessReportRead` fires zero-or-one times before the terminal — present iff the container wrote `report.json` before its exit; absent on timeout and typically absent on crash.

### G.6 Grade projection event (topology-level, roadmap S6)

Emitted once per cell topology, after the terminal event of the internal `HarnessProducer`. The `LogProjectionOracle` at post-S6 `assay/swebench.py:swebench_log_projection_oracle` reads exactly this event off the record — the oracle collapses to a one-event projection because the grade is now derivable from the record.

| Tag | Payload | Stratum |
|---|---|---|
| `GradeResult` | `instance_id: str, verdict: Verdict, reason: Reason` | summary |

**Invariants.** Exactly one `GradeResult` per cell record, positioned after `SelectedPatch` and after the `HarnessProducer`'s terminal event. `verdict` is a `Verdict` enum member (`PASS | FAIL | NO_VERDICT`); the wire form is the `.value` string per § E.1. `reason` is `""` (empty) when `verdict ∈ {Verdict.PASS, Verdict.FAIL}`; one of the `REASON_*` constants (§ E.2 closed set) when `verdict == Verdict.NO_VERDICT`. The `LogProjectionOracle`'s `extract` function projects `GradeResult` → `Result(verdict=..., reason=..., replayable=True)` with no conversion — the payload types match the `Result` field types directly.

**Rationale.** With every boundary productized (G.1–G.5), the grade itself is one more producer inside the topology. The oracle no longer runs Docker externally; it reads one event off the record. `assert_replayable` on a cell's record passes at L1 (grade projectable from the record). `first_divergence` between two runs of the same instance shows the exact producer where they diverge. Sources: `docs/review/ROADMAP-2026-08-12-swebench-rebuild-sprint-chain-v2.md` § "Sprint 6"; `docs/POSTMORTEM-2026-08-10-swebench-topology-drift.md` § RC3.

## F. Ratification signature

- **v0.1** — Sprint 133 close, 2026-06-27. Architect via review gate #1 (see
  `process/sprints/sprint-133-swebench-solver-vocabulary.md` closeout).
- **v0.2** — Consolidated 2026-08-12 by Sprint 161. Composed of two prior halts already ratified in
  `## Decisions`: H-1 + H-2 (2026-08-10, Verdict enum + passed as derived property); H-3 (2026-08-10,
  shared reason lexicon) extended 2026-08-11 with `rate_limited`. This doc flips the header to
  RATIFIED and records the two additions.
- **v0.3** — PROPOSED 2026-08-12 by Sprint 163 (roadmap v2 S0.75). Adds § G — six event families for the SWE-bench boundary producers (RateLimit, Container, Image, RepoClone, Harness) plus the topology-level `GradeResult`. Amended 2026-08-12 by Sprint 165 (fold of external review F5): the § G "Type conventions" note names `Verdict` (the § E.1 enum) and `Reason` (the § E.2 closed-set string) as symbolic payload types instead of bare `str`, so a typo at emit fails at the enum boundary rather than reaching the reader. `HarnessCompleted` and `GradeResult` payloads updated; invariants rewritten to name enum members and `REASON_*` constants. Awaiting Architect ratification in `## Decisions` before producer sprints S5.2–S5.6 dispatch. On ratification, the header status flips to `RATIFIED — v0.3` and § F gains a v0.3 sign-off line.
