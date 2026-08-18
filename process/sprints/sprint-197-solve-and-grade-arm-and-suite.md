# Sprint 197 — Arm + suite builders for the solve-and-grade topology (roadmap v2 S6 consumer)

Sprint 195/196 landed `GradeResult`, the grade producer factory, `swebench_solve_and_grade_topology`, and `SwebenchLogProjectionOracle`. Sprint 197 wires the live consumer: an arm and a suite the runner can dispatch that produces `GradeResult` on the record and projects it off.

## files touched

- `src/substrate/assay/swebench_suite.py` — new `swebench_solve_and_grade_arm(...)` builds a topology per case using `swebench_solve_and_grade_topology`; same responder + rate-limit-shim wiring as `swebench_solver_arm`; passes the case's `instance_id` from `ground_truth` into the topology so the grade producer's harness call uses a deterministic run_id per (arm, case). New `swebench_solve_and_grade_suite(cases, arms, control_arm, ...)` returns a `Suite` with `oracle=swebench_log_projection_oracle()` — no `report_root` param because the projection oracle reads the record directly. Both symbols added to `__all__`. `Mapping` added to the imports.

## contracts

- 4/4 new substance tests pass: arm.build returns a callable topology; the topology registers the `grader` producer kind with `GradeResult` schema; the suite's oracle is `SwebenchLogProjectionOracle`; both symbols exported.
- 46 targeted swebench + grade + arm tests still pass.
- Ruff + mypy strict clean on the single source file touched.
- `swebench_solver_arm` and `swebench_suite` (the pre-Sprint-197 arm/suite that use `SwebenchRecordOracle`) unchanged; the new arm/suite are additive.

## what a runner adoption looks like

`scripts/assay_swebench_confirmatory.py` can now build the SWE-bench Suite via `swebench_solve_and_grade_suite(cases, arms, control_arm="…")` where `arms` include `swebench_solve_and_grade_arm(...)`. The runner's `_print_report` path continues to work — the report reads `Result` objects the oracle produces; the projection oracle produces the same shape as the record oracle.

Migration is opt-in: the runner today builds `swebench_suite(...)` (old) with arms from `swebench_matrix.py` (which builds `swebench_solver_topology_with_test_selection` — the retired heavy path — under the current `_build_solver_arm_from_payload`). Full runner migration is a later sprint. Sprint 197 lands the primitive-plus-live-consumer shape (Sprint 183 discipline) so the S6 chain reaches a live opt-in path even before the runner adopts.
