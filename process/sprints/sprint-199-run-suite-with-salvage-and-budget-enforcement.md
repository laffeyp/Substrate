# Sprint 199 — `run_suite_with_salvage` + kernel `Budget.wall_seconds` enforcement (roadmap v2 S7a + S1b fold-in)

The confirmatory SWE-bench runner (`scripts/assay_swebench_confirmatory.py`) grew to 1045 lines because every generic control-flow piece was written inline: per-cell concurrency semaphore, salvage short-circuit, per-cell `asyncio.wait_for`, typed exception classification, lock-serialized JSONL row-write. Sprint 199 lifts the generic pieces into `assay/run.py` so Sprint 199b (S7b, next) can rewrite the runner around them in ~350-400 lines.

The kernel `Budget` primitive shipped at Sprint 164 as registration-only with a Sprint 172 UserWarning warning callers that runtime enforcement was pending. Sprint 199 folds in S1b: `Budget.wall_seconds` is now enforced inside `Runtime._producer_task`. A producer that runs past its declared wall cap yields `substrate.ProducerFailed` with a typed `error="budget_exceeded: wall_seconds=<limit>s: <reason>"`. `event_counts` enforcement (per-kind emit cap) is a later sprint — declaring `Budget.event_counts` still emits the standing warning.

## files touched

- `src/substrate/assay/run.py` — new `PerCellBudget(time_s, reason)` frozen msgspec Struct; new `CellOutcome` frozen dataclass (uniform across RUN / SALVAGE / ERROR sources); new `run_suite_with_salvage(suite, root_dir, *, trials, concurrency, salvage_dir, budget_for_cell, classify_exception, on_outcome, skip)` — the extracted generic loop; new `verdict_for_outcome` helper. Import surface: `Awaitable`, `Callable`, `Literal`, `Verdict`.
- `src/substrate/kernel/runtime.py` — `_producer_task` now reads `producer_kind.budget.wall_seconds` at task start and wraps the async-for consumer in `asyncio.wait_for(_consume(), timeout=cap.limit)`. On `asyncio.TimeoutError` emits `ProducerFailed` with the typed `budget_exceeded:` prefix (`cap.reason` rides on the wire).
- `src/substrate/kernel/topology.py` — Sprint 172 UserWarning narrowed. Fires only when `Budget.event_counts` is declared (still unenforced); a wall-seconds-only Budget is honest and silent.
- `tests/test_kernel_budget.py` — Sprint 172's warning test replaced by two: one asserts wall-only Budget no longer warns, one asserts event_counts Budget still warns.
- `tests/test_kernel_budget_wall_seconds.py` (new, 6 tests) — end-to-end: wall cap trips → ProducerFailed with typed prefix; wall cap far above runtime → normal ProducerCompleted; no budget → pre-Sprint-199 behaviour; declarations warn correctly per axis; record on disk carries the typed error.
- `tests/test_run_suite_with_salvage.py` (new, 9 tests) — pins the extracted loop contract: every triple runs; salvage regrades without calling topology (proven by disagreement between salvage record and case ground_truth); halt classifier re-raises original exception; flake classifier continues sweep; per-cell budget timeout becomes ERROR outcome carrying the budget; `on_outcome` hook fires once per completed cell; `skip` bypasses triples; `concurrency` cap holds; default classifier halts on any exception.

## contracts

- 27 new tests pass; 833 pass across the full suite (4 skipped, no failures) in 305s.
- Ruff clean on every touched file.
- Mypy strict clean on the three source files.
- Additive at the API surface: every existing caller of `run_arm_on_case` / `run_suite` still works; every existing producer_kind without a Budget declaration is untouched; every existing Budget-declaring producer_kind is untouched (Sprint 164 registration semantics preserved).
- Sprint 172 UserWarning now fires only for the axis that remains unshipped (`event_counts`); the primitive-plus-consumer discipline (Sprint 183) is honored for `wall_seconds`.

## what S7b (Sprint 199b, next) rewrites

`scripts/assay_swebench_confirmatory.py` around 1045 lines shrinks to ~350-400 by consuming:

```python
outcomes = await run_suite_with_salvage(
    suite=swebench_solve_and_grade_suite(cases, arms, control_arm=control),
    root_dir=SCRATCH,
    trials=TRIALS,
    concurrency=CONCURRENCY,
    salvage_dir=Path(SALVAGE) if SALVAGE else None,
    budget_for_cell=lambda a, c: PerCellBudget(
        time_s=min(RUN_TIMEOUT, timeout_for_instance(_instance_id(c))),
        reason="per-repo table capped by SWEBENCH_RUN_TIMEOUT",
    ),
    classify_exception=_classify_cell_error,
    on_outcome=_shape_and_append_row,
    skip=lambda a, c, t: (a.name, c.case_id, t) in done,
)
```

The five arms in `swebench_matrix.py` migrate to `swebench_solve_and_grade_arm` in the same commit, retiring `_build_solver_arm_from_payload`'s use of the heavy `swebench_solver_topology_with_test_selection`.

## roadmap position

S0-S6 landed with the live consumer path (Sprint 197). S8 landed (Sprint 198). S7a lands here. Next: S7b runner rewrite; then S9 wire-check at N=300 Lite and S10 Verified pass 1 (both behavior verification on the Architect's box).
