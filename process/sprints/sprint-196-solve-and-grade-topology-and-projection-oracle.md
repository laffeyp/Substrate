# Sprint 196 — `swebench_solve_and_grade_topology` + `SwebenchLogProjectionOracle` (roadmap v2 S6 part 2 of 2)

Sprint 195's `grade_producer_factory` + `GradeResult` primitives get consumed here.

## files touched

- `src/substrate/topologies/swebench_solver/assemble.py` — new `swebench_solve_and_grade_topology(...)` calls `swebench_repair_topology(...)` for the localize+repair phases and adds a `grader` producer triggered on `SelectedPatch`. The topology's termination policy overrides the repair topology's — `any_of(threshold_count("GradeResult", 1), quiescence_with_watchdog(watchdog + grade_timeout))` — because `RepairSummary` fires right after `SelectedPatch` and would race-cancel the grader under the repair topology's original termination.
- `src/substrate/assay/swebench.py` — new `SwebenchLogProjectionOracle` class + `swebench_log_projection_oracle()` factory. Reads exactly one `GradeResult` off the cell's record, maps `verdict` wire string → `Verdict` enum, returns `Result` with `replayable=True` (audit-replay, not grade-replay per roadmap v2 Sprint 181 correction). Fallback: no `GradeResult` on record → `Verdict.FAIL` naming the "no patch to grade" honest state.

## contracts

- 4/4 new substance tests pass (`test_solve_and_grade_topology.py`): topology-builds pin, oracle-reads-pass pin, oracle-reads-no_verdict-with-reason pin, oracle-fallback-on-empty-record pin.
- 45 targeted swebench + grade tests still pass (grade_producer, solve_and_grade, assay_swebench, swebench_solver, swebench_repair, swebench_repair_topology_dual_mode, bundled_swebench_repair).
- Ruff + mypy strict clean on both source files.
- Every existing arm helper using `swebench_repair_topology` behaves identically — `swebench_solve_and_grade_topology` is a new function consumers opt into.

## what changes about the grade path once consumers migrate

- **Before:** `SwebenchRecordOracle.grade` calls `run_swebench_one` at grade time — the harness runs INSIDE the oracle, `replayable=False`, the grade lands off the cell's record.
- **After (this landing):** the topology emits `GradeResult` during its own run; the oracle reads it off the record. `replayable=True` for the audit; `explain_producer` on `GradeResult` walks back through the grader producer, through `SelectedPatch`, through the whole solve path. The harness call still happens inside the grader producer (Sprint 195 wraps `run_swebench_one` via `asyncio.to_thread`); the harness's own five typed stderr events from Sprint 193 still fire.

## done

Three files. Real S6 landing: grade becomes a topology producer emitting `GradeResult` on the record; oracle collapses to a projection. Consumers who want the new shape swap `swebench_repair_topology` → `swebench_solve_and_grade_topology` and `swebench_record_oracle` → `swebench_log_projection_oracle`. Arm helpers migrate in a follow-on when the runner adopts.
