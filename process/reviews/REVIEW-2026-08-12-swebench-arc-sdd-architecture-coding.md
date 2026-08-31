# REVIEW — SWE-bench arc: SDD adherence, architecture, coding standards (2026-08-12)

*Reviewer role. Findings for the build side. No code edited here. New file per no-in-place-edits discipline.*

*Companion documents this review reads against and cross-cites:*
- `docs/POSTMORTEM-2026-08-10-swebench-topology-drift.md` — RC1/RC2/RC3
- `docs/DESIGN-2026-08-10-swebench-confirmatory-revert-v3.md` — H-1/H-2/H-3/H-4
- `docs/DESIGN-2026-08-11-responder-rate-limit-shim.md` — the shim
- `docs/review/ROADMAP-2026-08-12-swebench-rebuild-sprint-chain-v2.md` — 14-sprint chain
- `docs/review/AUDIT-2026-08-12-substrate-usage-in-swebench-work.md` — primitive gap
- `process/signals/swebench-solver-vocabulary.md` — v0.2 RATIFIED, v0.3 PROPOSED
- `process/WORKING_AGREEMENT.md` § "SWE-bench external substrates"
- Sprint cards 161–164
- `sdd-kit-2/AGENTS.md`, `sdd-kit-2/grammar/PRINCIPLES.md`, `sdd-kit-2/TECHNIQUES.md`, `sdd-kit-2/ADDENDUMS.md` D

*Files walked in full:* `assay/swebench.py` (986L), `assay/oracle.py` (186L), `assay/swebench_errors.py` (90L), `adapters/rate_limit.py` (211L), `scripts/assay_swebench_confirmatory.py` (972L), `kernel/topology.py` (373L), `api.py` (188L), `tests/test_kernel_budget.py` (118L), the two design docs, the postmortem, the audit, roadmap v2, the vocabulary doc, WORKING_AGREEMENT, sprint cards 162–164. Targeted greps for retyped literals, `except` scope, publish-refusal implementation, and DeprecationWarning elevation.

---

## Verdict

The arc's paper record is disciplined. The 2026-08-10 postmortem names three root causes cleanly; H-1/H-2/H-3 landed as `vocabulary_change_required` proposals ratified in `## Decisions`, not silent field appends; the 2026-08-12 halt escalated the shim's slot-holding bug into an architectural realignment rather than another patch; roadmap v2 casts every external boundary as a substrate producer with typed events on the record. Every one of those moves earns the discipline the kit teaches.

The code the paper record describes has not yet caught up. The rate-limit shim's slot-holding bug is on disk unchanged; a `BaseException` catch in the runner violates the invariant Sprint 162 wrote to ban it in the same file; the design-v3 publish-refusal branch is specified but not implemented; the heavy topology's DeprecationWarning is not elevated to error, so four scripts still import it silently; the vocabulary v0.3 proposal encodes the `Verdict` enum back to `str` at the emit boundary; and the kernel `Budget` primitive at Sprint 164 uses unnamed tuples for named concepts. Every one of these is small on its own. Together they are the "the paper says one thing, the code does another" pattern the SWE-bench arc has been fighting for six weeks.

Two moves close the largest gaps this week without waiting for roadmap v2's S5.x producer chain: (1) release the semaphore during 429 sleep in `adapters/rate_limit.py:158,180` so pass-1 Verified is not blocked on producer authoring; (2) narrow the `BaseException` at `scripts/assay_swebench_confirmatory.py:841` to `Exception`. Both are one-line fixes at known coordinates. The producer chain then lands roadmap v2 into a substrate that already survives Ctrl-C and 429 pressure honestly.

---

## Findings

Numbered by severity, most-severe first. Each carries file:line, evidence, and a next move the build side can act on.

### F1 — The rate-limit shim's slot-holding bug is still live and shipping (BLOCKER)

**Where.** `src/substrate/adapters/rate_limit.py:153-190`. Method `RateLimitedResponder.arespond`.

**What.** Line 158 acquires the semaphore with `async with sem:` around the entire retry loop; line 180 does `await asyncio.sleep(delay)` INSIDE that scope on 429/503. The slot is pinned for the length of the sleep while nothing is in flight. Under sustained 429 pressure the three workers on Pro pin all three slots; five queue; throughput collapses to `capacity / sleep_multiplier` exactly as the 2026-08-12 halt described.

**Evidence.** The halt at `process/BLACKBOARD.md ## Surfaced for review` names this precisely — reason (3), "Shim retry holds slot ... acquires the semaphore around the entire retry loop, so a 429 sleep pins the slot for 30-60s while nothing is in flight." The 2026-08-10 N=300 Pro run threw 3337 of 4088 HTTP calls to 429; every multi-call arm collapsed to zero passes.

**Why this is still F1 today.** Roadmap v2 S5.2 recasts the shim as `RateLimitProducer` and moves the retry logic outside the semaphore scope. That is one to two sprints out. In the meantime, the shim is what every arm's Responder gets wrapped in; any Verified pass-1 attempt hits the same wall. Retirement-in-place discipline (KIT_DIARY finding 38) says the shim should raise the cost of accidental re-use above the cost of the deprecation notice. Right now the shim is not retired — it is the only path in flight.

**Next move.** Move the `await asyncio.sleep(delay)` outside the `async with sem:` block. Twenty lines, one semaphore release + reacquire pair per retry. Test at `tests/test_rate_limit.py` extended with a three-worker pileup scenario under sustained 429. Unblocks Verified pass 1 without waiting for producer authoring. Optional harden: add a `DeprecationWarning` at construction so any new consumer trips a `filterwarnings = ["error::DeprecationWarning"]` gate the way KIT_DIARY finding 38 named for the heavy topology.

### F2 — Sprint 162's own invariant is violated by the file it names (BLOCKER)

**Where.** `scripts/assay_swebench_confirmatory.py:841`. `_classify_cell_error`'s outer catch.

**What.** The runner catches `BaseException`. Sprint 162's cross-cutting invariants at `process/WORKING_AGREEMENT.md:130` say: "No new SWE-bench code catches `BaseException` around a boundary call." This is the same runner Sprint 162 was written to constrain. `BaseException` catches `KeyboardInterrupt`, `SystemExit`, `asyncio.CancelledError`; the classifier turns them into `NO_VERDICT` rows and continues the sweep. A Ctrl-C during a 4088-call run writes 4088 rows instead of unwinding.

**Evidence.** The typed exception hierarchy at `assay/swebench_errors.py` (`SwebenchRunnerError`, `DockerDaemonError`, `ContainerCrashed`, `GitOperationFailed`, `HarnessTimeout`, `HarnessError`) all inherit from `RuntimeError` → `Exception`. `ProviderRateLimited` at `adapters/rate_limit.py:85` inherits from `RuntimeError`. `FirewallViolation` at `assay/swebench.py:134` inherits from `ValueError`. None of them need `BaseException` to be caught.

**Next move.** Change `except BaseException as exc:` to `except Exception as exc:` at line 841. Add a `_classify_cell_error(KeyboardInterrupt())` test that asserts `TypeError` is raised (the classifier declines to touch it). One-line fix.

### F3 — The publish-refusal branch design v3 requires is not implemented (BLOCKER)

**Where.** `src/substrate/assay/report.py` — no `RUN_UNPUBLISHABLE` symbol, no threshold check, no publish-refusal path.

**What.** `docs/DESIGN-2026-08-10-swebench-confirmatory-revert-v3.md` § "The report contract" specifies: "The report refuses to publish 'confirmatory' if graded_rate below threshold. Pre-reg pins the threshold. When `M/N < threshold`, the report emits a `RUN_UNPUBLISHABLE` verdict block with the completion gap named." The pre-registration pins the per-arm graded-rate floor.

**Evidence.** `grep -rn "RUN_UNPUBLISHABLE\|publish.*threshold\|graded_rate.*threshold" src/ scripts/` returns zero hits. Design v3 § "The runner contract" also names the branch. Nothing in `report.py` reads a threshold or refuses publication.

**Why this matters.** The 2026-08-10 N=300 Pro run was 82% 429s. Under design v3, that run's report would emit `RUN_UNPUBLISHABLE`. Under the current code, the same report would publish a headline computed against a badly-throttled M, and the reader would have to notice from `reason_counts={rate_limited: N}` that the number is not credible. The whole design-v3 discipline of "the report is self-diagnosing" rests on this branch existing.

**Next move.** Land `RUN_UNPUBLISHABLE` at `report.py`. Read `graded_rate_floor` from the pre-registration file (`docs/preregistrations/2026-08-swebench-lite.preg.json` — the file that already pins the arms_hash). If `(N_attempted - N_no_verdict) / N_attempted < graded_rate_floor` for any arm, emit `RUN_UNPUBLISHABLE` block naming the gap. Test at `tests/test_assay_report.py` seeds a synthetic cells.jsonl with 82% NO_VERDICT rows and asserts the report refuses to publish.

### F4 — Retyped literal past mypy at the exact class the halt names (HIGH)

**Where.** `src/substrate/assay/report.py:413`.

**What.** The line reads: `r.result.reason or _extract_reason(r.result.detail) or "harness_error"`. The raw string `"harness_error"` appears where the constant `REASON_HARNESS_ERROR` from `assay/swebench.py:65` should live. Vocabulary v0.2 § E.2 mandates the closed set at `swebench.py:_HARNESS_REASONS`; the ratification note says "every writer imports the named constant, not the raw literal." This one path bypasses the discipline.

**Evidence.** Full grep `grep -rn '"harness_error"' src/ scripts/ tests/` returns exactly this one hit outside the constant definition. The kit's `feedback-read-the-code-grep-repeated-literals` (per memory) names this class as invisible to mypy and ruff — a rename of `REASON_HARNESS_ERROR` would silently miss this call site.

**Next move.** `from .swebench import REASON_HARNESS_ERROR`; replace `"harness_error"` with `REASON_HARNESS_ERROR`. One-line edit. Extend the grep to CI: `rg -F '"harness_error"' --type py src/ scripts/ | grep -v REASON_HARNESS_ERROR | wc -l` must be 0.

### F5 — Vocabulary v0.3 § G re-encodes the Verdict enum to str at the emit boundary (HIGH)

**Where.** `process/signals/swebench-solver-vocabulary.md:237`. `HarnessCompleted` payload: `verdict: str`. Same shape for `GradeResult` at line 249: `verdict: str`.

**What.** § E.1 of the same doc (v0.2 RATIFIED) defines `Verdict` as an enum with three values. Every reader at the oracle boundary imports the enum. The v0.3 proposal asks the producer to encode it as a bare `str` at the emit boundary. Two representations of the same fact, one enum, one string — exactly the H-1 drift shape ("two fields carrying one fact") the ratification was written to prevent.

**Why this matters.** The invariants paragraph at § G.5 says `verdict ∈ {"pass", "fail", "no_verdict"}`. Nothing at emit enforces the closed set. A producer that emits `verdict="passed"` or `verdict="PASS"` is a typo away from a silent grader bug. The v0.3 producer chain (Sprints 5.2–5.6) inherits this shape.

**Next move.** Change the payload declaration in § G.5 and § G.6 from `verdict: str` to `verdict: Verdict` (the enum from § E.1). msgspec supports enum-typed fields; the wire form is the enum's `.value` string. If enum-in-payload is rejected on portability grounds, use `verdict: Literal["pass", "fail", "no_verdict"]` — the closed set is at the type layer, not in a paragraph. Same treatment for `reason: str` fields that reference `_HARNESS_REASONS`; `Literal[...]` with the seven wire strings makes the closed set enforceable at emit.

### F6 — Kernel Budget primitive uses unnamed tuples for named concepts (HIGH)

**Where.** `src/substrate/kernel/topology.py:53-54`.

```
wall_seconds: tuple[float, str] | None = None
event_counts: dict[str, tuple[int, str]] | None = None
```

**What.** The `str` slot in each tuple is a reason string. Field access at the enforcement site (Sprint 165) reads `budget.wall_seconds[0]` for the cap and `budget.wall_seconds[1]` for the reason. The tuple slot is opaque at the read site; the enforcement code has to remember which index is which.

**Evidence.** Tests at `tests/test_kernel_budget.py:59-89` all construct with positional-tuple literals: `Budget(wall_seconds=(30.0, "unit-test wall cap"))`. This is the same shape violation as F5 — a raw pair carrying named concepts.

**Why this matters.** The Sprint 164 sprint card notes at line 25 that the primitive lands "on the shelf" for Sprint 165's enforcement to consume. Sprint 165 will emit `substrate.BudgetExceeded(reason=...)` events; the reason string flows from `budget.wall_seconds[1]` at the enforcement site. If Sprint 165 reads `[0]` for reason by mistake, mypy passes (both are `Any`-ish inside the tuple), and the event carries a number where the reason should be. The kernel is the substrate that enforces vocabulary discipline; it should not itself use unnamed tuples for named concepts.

**Next move.** Add a small frozen msgspec.Struct at `topology.py`:

```
class Cap(Struct, frozen=True):
    limit: float
    reason: str
```

`wall_seconds: Cap | None`; `event_counts: dict[str, Cap] | None`. Field access reads as `budget.wall_seconds.reason` at every consumer. Ratifies the shape before Sprint 165's enforcement lands on top of it; this is the cheapest possible time to change it.

### F7 — Sprint 164 declares a primitive with no runtime check; Sprint 165 has not landed (HIGH)

**Where.** Sprint 164 shipped at `topology.py:29-54` + `api.py:74`. Sprint 165 (runtime enforcement) has not shipped.

**What.** A producer that declares `budget=Budget(wall_seconds=(30.0, "cap"))` today runs unbounded — the runtime does not check. The Sprint 164 card at line 158 acknowledges this: "Sprint 164 producers that declare a budget do not overrun — the runtime does not check yet." The primitive advertises enforcement it does not perform.

**Why this matters.** A build-side worker who reads the WORKING_AGREEMENT § "Producer-authorship rules" at line 123 ("Every producer declares a Budget ... Runtime enforces at run time; overrun emits substrate.BudgetExceeded and terminates the producer factory") is told the runtime enforces. Between Sprint 164 and Sprint 165 the promise is false. A producer that trusts the promise misconfigures its cap and looks safe until N=300 exposes it — the same class-of-failure this whole arc is fighting.

**Next move.** Two options, both cheap: (a) emit a `RegistrationError` at `producer_kind` build time when `budget` is set but the runtime lacks enforcement — a hard fail says "do not use this yet"; or (b) emit a `UserWarning` at build time naming Sprint 165 as the ETA. Option (a) is stricter and matches the substrate's own preference for build-time over run-time detection (design §5.5). Land it in the same sprint that lands Sprint 165 so the warning window is a day, not a week.

### F8 — WORKING_AGREEMENT names Budget axes that the shipped primitive does not carry (HIGH)

**Where.** `process/WORKING_AGREEMENT.md:123`.

**What.** The line reads: "Every producer declares a Budget (from the S1 kernel change: `docker_containers`, `wall_seconds`, `model_calls` caps)." Sprint 164 shipped `wall_seconds` and `event_counts`. `docker_containers` and `model_calls` do not exist as named axes on the primitive; they would be entries under `event_counts` keyed by event-kind name (e.g. `event_counts={"ContainerRequested": (1, "..."), "ModelUsage": (K, "...")}`).

**Evidence.** `topology.py:53-54` defines exactly two axes. Sprint 164 tests at `test_kernel_budget.py:80-88` demonstrate the intended pattern: `event_counts={"ContainerRequested": (1, "one grade container per instance"), "ModelUsage": (7, "n*max_rounds+localize")}`.

**Why this matters.** A build-side worker for S5.3 (ContainerProducer) reads WORKING_AGREEMENT looking for the Budget API they must declare, finds `docker_containers` as a named axis, and writes `Budget(docker_containers=(1, ...))` — which is a TypeError. The doc looks authoritative and misleads the consumer.

**Next move.** Rewrite line 123: "Every producer declares a `Budget` (from S1: `wall_seconds` for wall-clock, `event_counts={event_kind: (cap, reason)}` per-emit cap). ContainerProducer caps `event_counts={'ContainerRequested': (1, ...)}`; HarnessProducer caps `wall_seconds` from the per-repo timeout table; RateLimitProducer caps `event_counts={'RateLimitAttempted': (K, ...)}`." Same information, matching the shape that shipped.

### F9 — The heavy topology's DeprecationWarning is not elevated; four callers still import (HIGH)

**Where.** `pyproject.toml` — no `filterwarnings` entry. Callers still on file:
- `scripts/docker_runner_smoke.py:10`
- `scripts/regression_seam_smoke.py:22`
- `scripts/flask_solve.py:115,137`
- `scripts/solve_instance.py:28,37,100`

**What.** KIT_DIARY finding 38 (2026-08-11) named the retire-in-place discipline for `swebench_solver_topology_with_test_selection`: "nine existing tests in `test_swebench_solver.py` now emit `DeprecationWarning` when they build the heavy topology; a suite with `filterwarnings = ['error::DeprecationWarning']` would fail loudly on any new consumer, which is the enforcement the retirement rides on." The `_deprecated/README.md:47` explicitly names this as the enforcement.

**Evidence.** `assemble.py:488` emits the warning. `pyproject.toml` does not carry `filterwarnings`. The audit at 2026-08-12 § "Remove or move" says "verify the five files under `topologies/swebench_solver/` that supported it ... are unwired" — they are not; four scripts still import them.

**Why this matters.** The retirement rides on a warning nothing elevates. Anyone touching the four scripts triggers the warning silently — no CI failure, no output the human notices. The heavy topology can be re-adopted by any next commit without tripping any gate.

**Next move.** Two moves in one commit: (a) migrate the four scripts to `swebench_repair_topology` (they built the heavy path for reproduction-based selection they no longer need — the design-v3 revert makes the light path the standard); (b) add `filterwarnings = ["error::DeprecationWarning:substrate.topologies.swebench_solver.assemble"]` to `pyproject.toml`'s `[tool.pytest.ini_options]`. The nine existing tests KIT_DIARY 38 names then need to opt out via `pytest.warns(DeprecationWarning)` — a per-test opt-in matches the pattern.

### F10 — `verify_constants()` silences all Exception, not just ImportError (MEDIUM)

**Where.** `src/substrate/assay/swebench.py:305-307`.

**What.** The block: `try: import swebench.harness.constants as sw / except Exception: return`. Any exception during import — a real dependency error, an AttributeError, a schema drift inside swebench's own imports — falls through silently. The check exists to catch drift between our field-name constants and swebench's; a silent skip on an unexpected error defeats the check exactly when it was needed.

**Next move.** Narrow to `except ImportError:` — a swebench absence is legitimately silent (the module is env-gated); anything else is data. If a broader catch is required for a specific reason, name that reason in a comment and catch only the specific type.

### F11 — `batch_grade_from_records` swallows Exception on record read (MEDIUM)

**Where.** `src/substrate/assay/swebench.py:884-887`. Inside `batch_grade_from_records`.

**What.** `try: events = list(read_record(cell_dir)) / except Exception: continue`. A cell whose record can't be read is silently skipped from the batch grade; the report under-counts. Record corruption, disk-full errors, unrelated bugs in `read_record` — all vanish.

**Evidence.** `substrate.api` exports typed record errors: `RecordIncompleteError`, `RecordGapError`. These are the legitimate silences; anything else is a bug the reader should see.

**Next move.** Narrow to `except (RecordIncompleteError, RecordGapError):`. Add a log line naming the cell dir when this fires. Anything else re-raises.

### F12 — Roadmap v2's wire-check gate (S9) doesn't guard against the exact failure that produced this halt (MEDIUM)

**Where.** `docs/review/ROADMAP-2026-08-12-swebench-rebuild-sprint-chain-v2.md` § "Sprint 9 — Wire-check on Lite at N=300".

**What.** The observation-contract additions are: one `SelectedPatch`, one `HarnessCallFired`, one `HarnessCompleted`, one `GradeResult` per cell; no cell has > 10 `RateLimitDenied`; `ContainerKilled` count = 0. Missing: any bound on sustained 429 rate against the tier's real capacity.

**Why this matters.** KIT_DIARY finding 39 (2026-08-11) is the load-bearing lesson: "every future observation contract should be sized not only for the primary claim's CI but for the second-order failures the run's scale exposes." A 300-cell wire-check that respects a ≤10 per-cell 429 count can still burn tier throughput at 82% (300 cells × 10 dens = 3000 dens, over ~30 min of sweep, is roughly a 100/min denial rate — a saturation pattern). The gate should read the sustained rate, not a per-cell count.

**Next move.** Add to S9's observation contract: "sustained `RateLimitDenied` rate over any 30-minute window must not exceed `20% of provider capacity`; a run that crosses this threshold refuses to publish and dumps a per-model-per-minute denial curve." The threshold matches the discipline in F3 (publish-refusal on graded_rate); the denial curve gives the next postmortem a starting fixture.

### F13 — No CI guard preserves the "no deletions" audit-trail discipline (LOW)

**Where.** Standing gap; `pyproject.toml`, `.pre-commit-config.yaml`, `scripts/ci_local.sh`.

**What.** AGENTS.md hard rule 12 says restructures land as new files / round-N versions; the audit trail is the work. `_deprecated/` directories under `topologies/` are the concrete pattern. Nothing prevents a fast-follow commit from `rm`-ing a `_deprecated/` file. The discipline lives in code review, not in the tree.

**Why this matters.** Roadmap v2 S5.2b moves `RateLimitedResponder` under `_deprecated/` with body preserved; S7 does the same for the 972-line runner. A commit that reduces line count by deleting `_deprecated/` files would look like cleanup and would silently destroy the audit trail these findings all reference back to.

**Next move.** Add a check to `scripts/ci_local.sh` or `pyproject.toml`'s pre-commit stack: `git diff --diff-filter=D --name-only origin/main...HEAD | grep _deprecated/ && exit 1`. Twenty seconds of CI, forever. The audit trail then depends on the tree, not on reviewer memory.

### F14 — Stale writer at scripts/bench_coding.py writes untyped source strings (LOW)

**Where.** `scripts/bench_coding.py:275,288` and the reader at line 162-163.

**What.** The coding assay runner writes rows with `source="fail"` and `source="salvage"`/`"run"` as raw strings. Sprint 143 landed `CellSource` as a typed enum (KIT_DIARY finding 39 references it, commit `1ded31b`); the SWE-bench runner uses `CellSource.RUN`/`SALVAGE`/`ERROR` (`assay_swebench_confirmatory.py:324`). The coding runner never migrated. Two writers, two contracts, one enum for both.

**Why this matters.** The coding runner is the shape the SWE-bench runner was patterned on (bench_coding.py parity is called out in the SWE-bench runner's docstring at line 8). The next assay author who copies the coding pattern inherits the drift. Two writers producing the same cells file format under different disciplines is the vocabulary-as-contract violation the closed set exists to prevent.

**Next move.** Migrate `bench_coding.py:275,288` to `CellSource.FAIL.value` and equivalent; the reader at line 162-163 is already an equality check against strings, so the migration is one-directional and safe. Add a substance test at `tests/test_bench_coding.py` asserting the writer produces `CellSource`-valued rows.

### F15 — Prose register audit

The docs read plainly. Terms are consistent and match field usage: `producer` (event source), `topology` (registered graph of producers + triggers + views), `record` (append-only log the runtime writes), `verdict` (grade outcome, three-state), `reason` (closed-set string on `NO_VERDICT`), `boundary-as-producer` (coined-here but named consistently across three docs — vocab § G, WORKING_AGREEMENT, roadmap v2). No LLM-tells. No "schoolroom" language. No emojis in committed files. Design v3, postmortem, audit, roadmap v2 all lead with facts; the postmortem's numbered RCs and CFs are the shape a review can act on.

Two prose observations, not violations:

- **`PAPER-2026-08-12-swebench-failure-and-the-sdd-remedy.md`** exists in `docs/review/` (856 lines; not read for this review). The word "remedy" in the title imports a genre — the argumentative paper — that lives one shelf away from an engineering audit. Per memory: no market/product framing; correctness is the point. If the paper is technical throughout, name it after the technical content ("SWE-bench arc: divergence between paper record and code state" or similar); if it does frame SDD as a market position, restructure it as a technical postmortem. Un-flagged pending a read; noting the pattern.

- **"boundary-as-producer"** is a good coinage. It reads correctly in the vocab doc, WORKING_AGREEMENT, and roadmap v2. Names the discipline the arc is landing. Keep.

---

## What is holding well

Fair balance — this section is not a courtesy, it names the discipline the arc has earned.

**The halt-and-articulate move on 2026-08-12 is the arc's best decision.** The Architect could have accepted a shim patch and unblocked Verified pass 1 the same afternoon. Instead the halt escalates to "every SWE-bench external boundary should be a substrate producer emitting typed events on the record" — the deeper diagnosis. That is what hard rule 4 asks for and what the KIT_DIARY-worthy findings 37/38/39 all point at. The paper record from the halt to roadmap v2 is textbook.

**H-1/H-2/H-3 landed as vocabulary proposals, not silent field appends.** Each went through `## Surfaced for review` with typed evolution kinds (`NEW_TAG_PROPOSED`, `PAYLOAD_FIELD_PROPOSED`), ratified in `## Decisions`, then landed in code (`oracle.py:36-105`, `swebench.py:55-85`). Sprint 161's consolidation into the vocab doc closes the loop — the ratified text and the code agree. `grammar/PRINCIPLES.md` commitment 3 respected end to end.

**The typed exception hierarchy at `swebench_errors.py` is right-shaped.** Every boundary error carries a class-level `reason` attribute from `_HARNESS_REASONS`; the runner reads `exc.reason` at the classify site instead of grepping `repr(exc)`. The docstring at lines 74-80 names why `ProviderRateLimited` deliberately lives outside the SwebenchRunnerError tree — the shim is assay-independent, "a duplicate class here would just re-hide the coupling in a wrapper class no raise-site uses." Well-argued restraint.

**`run_swebench_one` owns container lifecycle correctly** (`swebench.py:397-505`). `subprocess.run(timeout=T)` around the harness call; `docker kill <container_name>` on `TimeoutExpired`; deterministic container names via `_container_name(instance_id, run_id)`; typed `HarnessOutcome` return with `verdict` + `reason` from the shared closed set. Matches design v3 § "The grader contract" line by line.

**Sprint 164 is well-scoped and disciplined.** ≤2 source files + one test file; additive-only; 113 broader kernel/api/topology tests pass identically; ruff + mypy strict clean. The card names the split rationale explicitly at line 148-151: "Split honors AGENTS.md hard rule 6." That is how the sweet spot rule is meant to work.

**Roadmap v2's shape is correct.** Fourteen sprints, one per producer, dependency graph named. The audit at `AUDIT-2026-08-12-substrate-usage-in-swebench-work.md` identifies exactly the right primitives the SWE-bench work under-used (`run_suite`, `embedded_substrate`, `cancel_all_others`, `explain_producer`, `first_divergence`, `narrate`, `attach`); roadmap v2's S6-S8 wires them in. The claim "runner shrinks from 972 lines to roughly 150" is credible given `bench_coding.py`'s 40 lines around a `run_suite` call.

**Findings 30/33/37/38/39 on the diary already name the ridges the arc has been landing on.** Green-suite-over-stochastic-seam (30), green-gate-is-the-floor (33), typed-reason-not-silent-zero-output (37), retirement-without-deletion (38), observation-contract-second-purpose (39). This review's findings mostly extend those; nothing here contradicts them. The diary discipline is what makes the compounding work.

---

## The two-move short list

If the build side takes nothing else from this review, take these two moves this week:

1. **`adapters/rate_limit.py:158,180`** — release the semaphore during 429 sleep. Twenty lines. Unblocks Verified pass 1 without waiting for the S5.2 producer.
2. **`scripts/assay_swebench_confirmatory.py:841`** — narrow `except BaseException` to `except Exception`. One line. Honors the invariant Sprint 162 wrote to bind the same file.

Everything else above can queue behind the roadmap v2 chain. These two cannot.

---

## One-line summary

The arc's paper record earns the discipline the kit teaches; the code has not yet caught up, and the gap is one shim fix + one exception-catch narrow + a publish-refusal branch away from being closed for this cycle, with a Budget primitive that needs a small enforcement gate and a vocabulary v0.3 that should type its verdicts instead of re-encoding them to str.

---

*Reviewer: Claude, this session. New dated file per no-in-place-edits discipline. Findings are for the build side to disposition; none are self-applied. Additive to `docs/review/` alongside AUDIT / PAPER / ROADMAPs v1 and v2 dated 2026-08-12.*
