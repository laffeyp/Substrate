# Sprint 199d — `container_solve_and_grade_arm` + in-topology grade for the backend arms (roadmap v2 S7b follow-on)

Sprint 199b landed `SWEBENCH_ARMS=solve_and_grade` mode carrying the four repair arms under `swebench_log_projection_oracle`. `container_arm` (structurally distinct topology — one producer emitting `SelectedPatch` from an agent loop in the eval container) could not join because its topology emitted no `GradeResult`; the whole matrix fell back to `SwebenchRecordOracle` on any mode that included it. Sprint 199d closes the gap.

## files touched

- `src/substrate/assay/swebench_matrix.py` — new `_backend_topology_with_grade(solve, *, instance_id, dataset_name, model_name, run_id, report_dir, grade_timeout_seconds, ...)` builds `_backend_topology`'s `solve` producer plus a `grader` producer wired via `grade_producer_factory`; trigger fires `grader` on `SelectedPatch` (policy `Once`); termination is `any_of(threshold_count("GradeResult", 1), quiescence_with_watchdog(...))` so the grader completes before the run finalises (and the no-patch quiescence path still terminates cleanly). New `container_solve_and_grade_arm(name, role, *, model, report_root, dataset_name, ...)` uses it — `run_id` binds (arm, instance) so parallel grades don't collide on the same report_dir, matching the shape at `swebench_solve_and_grade_arm`.
- `scripts/assay_swebench_confirmatory.py` — matrix_spec always includes `tool_loop_container` now (pre-Sprint-199d it was omitted from `solve_and_grade` mode). The arm-build branch dispatches on ARMS_MODE: `solve_and_grade` builds `container_solve_and_grade_arm`, every other mode builds `container_arm`. Import surface: `container_solve_and_grade_arm` added.
- `tests/test_container_solve_and_grade_arm.py` (new, 4 tests) — pins the extracted contract: `_backend_topology_with_grade` declares both `solve` and `grader` producer kinds; the trigger fires the grader on `SelectedPatch` with policy `Once`; the termination policy's `.name` names `GradeResult` and quiescence (both branches present); `container_solve_and_grade_arm.build(case)` reproduces the shape.

## contracts

- 4/4 new tests pass; 839 across the full suite (4 skipped, 0 failures) — one more than pre-Sprint-199d because the new tests landed and the prior test counts are stable.
- Ruff clean on every touched file; mypy strict clean on `swebench_matrix.py`.
- API preservation: `container_arm` unchanged (still available for pre-Sprint-199d record-oracle usage); `_backend_topology` unchanged (still available for host_arm / one-off callers who don't want in-topology grading).
- Behavior improvement: `SWEBENCH_ARMS=solve_and_grade` mode now carries the full six-arm matrix instead of five, and every arm's grade lands as a typed `GradeResult` event on its cell record; `swebench_log_projection_oracle` reads it off without an external harness call from the oracle. The audit-vs-grade split from Sprint 196 is preserved — the audit re-derives from the record, the grade itself (pytest inside Docker) remains non-deterministic.

## observation contract

Landed as `tests/test_container_solve_and_grade_arm_e2e.py` — a real Runtime run of `_backend_topology_with_grade` against the cached `pallets__flask-4045` eval image. A stub solve emits `SelectedPatch(model_patch="diff --git a/x b/x\n")`; the trigger fires the grader; `run_swebench_one` runs the real harness inside the flask-4045 container; `GradeResult(instance_id="pallets__flask-4045", verdict="fail", reason="")` lands on the record. Total wall: 96 seconds. The test skips when Docker or the flask-4045 image is missing. This wires the ENTIRE grade path (topology → trigger → grader factory → run_swebench_one → Docker harness → GradeResult on record) end-to-end; only the `solve_in_container` agent loop is stubbed (that surface belongs to `swebench_agent`, out of scope for this sprint).

An earlier draft of this card called the observation contract "deferred to S9." That was wrong on two counts: S9 fires `SWEBENCH_ARMS=solver`, not `solve_and_grade`, so it exercises none of Sprint 199d's new code path; and "deferred" is the closure state a gap I introduced does not earn (see KIT_DIARY 44). Fixed inline before the sprint closed.

## roadmap position

S0–S6 landed with the live consumer path (Sprint 197). S8 landed (Sprint 198). S7a landed (Sprint 199 — extraction). S7a-SDD-fold landed (Sprint 199a — canonical home + typed budget_exceeded). S7b landed (Sprint 199b — runner rewrite + heavy-path retirement). S7b-close landed (Sprint 199c — `swebench_solver_arm` migration). S7b-follow-on lands here (Sprint 199d — `container_solve_and_grade_arm`). S9 wire-check at N=300 Lite is running concurrent with this landing.
