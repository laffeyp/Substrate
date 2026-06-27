# swebench_solver — locked record vocabulary (sprint 1, the vocabulary session)

Status: PROPOSED for the vocabulary-session lock (review gate #1). Designed BEFORE code (#1). The
topology records are frozen msgspec Structs (topology-local, like coding_flow's), registered in
`process/WORKING_AGREEMENT.md`; this doc locks their fields, the #25 dual-contract audit, and the
shared-sub-topology reconciliation (review #57). Strict validator-extras (project posture).

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
| `Verdict` | `round:int, slot:int, passed:bool, returncode:int, summary:str` | the DETERMINISTIC validation of one candidate. coding_flow: the gate. swebench: the APPLIER result (`passed`=applied cleanly + git-diffs non-empty; `summary`=the structured reject reason fed to the next round). |
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
| `AppliedPatch` | `slot:int, model_patch:str, creates_file:bool` | a candidate that applied cleanly, carrying its `git diff` (`model_patch`) and whether it created a new file (the empty-SEARCH path, §4b). The REPAIR->SELECT bridge. | repair / event |

SELECT (after the loop):

| Record | Locked fields | Meaning | Category / stratum |
|---|---|---|---|
| `TestResults` | `slot:int, regression_passed:bool, reproduction:str, summary:str` | the solver's own validation of one applied patch: repo-derived regression result + reproduction-test status (`reproduced`/`resolved`/`other`). **`replayable=False`** — a run-and-observe Docker seam (§4), captured once. | select / incident-or-event |
| `SelectedPatch` | `slot:int, model_patch:str, reason:str` | the final submitted patch + why it won (majority vote / regression / reproduction). The topology's output to the swebench oracle. | select / summary |

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

## D. Open items for later sprints (named, not deferred-silently)

- The shared loop's terminal/collect-vs-stop policy — sprint 4 (extraction), a topology parameter.
- The in-container SELECT test-execution is a NEW bridge (#32/#46) — its bridge mapping is sprint 6,
  distinct from the grade-harness mapping in `docs/swebench-bridge-mapping.md`.
- `EditTarget` as a typed Struct vs the `list[str]` shorthand — `list[str]` for v1 (minimal-complete #6);
  promote to a Struct only if a downstream consumer needs structured fields.
