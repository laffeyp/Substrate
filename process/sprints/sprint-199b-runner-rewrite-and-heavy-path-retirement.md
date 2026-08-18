# Sprint 199b — Confirmatory runner rewrite around `run_suite_with_salvage`; heavy path retired (roadmap v2 S7b)

Sprint 199 (S7a) extracted the generic per-cell orchestrator into `assay/run.py::run_suite_with_salvage`. Sprint 199b rewrites `scripts/assay_swebench_confirmatory.py` to consume it, and retires the `include_test_selection=True` opt-in that let matrix arms route through the deprecated heavy topology.

## files touched

- `scripts/assay_swebench_confirmatory.py` — 1045 lines → 761 lines. The inline `cell()` loop (salvage short-circuit + `asyncio.wait_for` + `_classify_cell_error` dispatch + lock-serialized JSONL row-write) is gone. The runner calls `run_suite_with_salvage(...)` with callbacks: `budget_for_cell` computes `min(RUN_TIMEOUT, timeout_for_instance(...))` per cell, `classify_exception` is the SWE-bench-specific `_classify_cell_error`, `on_outcome` shapes each `CellOutcome` into a cells-JSONL row via the new `_shape_row`, `skip` reads the resume set. New `SWEBENCH_ARMS=solve_and_grade` mode builds arms with `swebench_solve_and_grade_arm` and grades via `swebench_log_projection_oracle` — Sprint 197's live consumer path finally consumed by the runner. `matrix` mode keeps `SwebenchRecordOracle` because `container_arm` (structurally distinct topology) needs the external harness. Model preflight, image prepull, prep sweep, cases sidecar, meta.json, foreign-config guard, BATCH_GRADE, `_print_report` all preserved unchanged in behavior.
- `src/substrate/assay/swebench_matrix.py` — removed `include_test_selection` parameter from both `_build_solver_arm_from_payload` and `swebench_repair_arm`. The `if include_test_selection:` branch that fired the DeprecationWarning and called `solver_topology_from_payload` is gone. `swebench_solver_arm` (pre-Sprint-197 arm) still routes through the heavy path via `solver_topology_from_payload` directly — a separate migration, out of scope for S7b.
- `src/substrate/topologies/swebench_solver/assemble.py` — docstring updated to name Sprint 199b as the retirement point for the matrix-arm opt-in.
- `tests/test_confirmatory_runner_exception_scope.py` — the `except Exception` pin followed the code from `assay_swebench_confirmatory.py` to `assay/run.py::run_suite_with_salvage`. Runner-side pin narrowed to "no `except BaseException` anywhere" (covers any new prep / preflight / batch-grade catch). Classifier contract pins on KeyboardInterrupt + SystemExit unchanged.
- `tests/test_per_cell_timeout.py` — the source-scan pin points at `budget_for_cell=_budget_for_cell` (the new callback shape); the callback body calls `timeout_for_instance(...)` capped by `RUN_TIMEOUT`.
- `tests/test_assay_swebench_matrix.py` — replaced `test_include_test_selection_true_opts_into_heavy_topology` (asserted a retired branch worked) with `test_include_test_selection_parameter_retired` (asserts the parameter is gone from both signatures).

## contracts

- 838 passed / 4 skipped in 270s on the full suite. Same count as post-Sprint-199a; net zero regressions from the runner rewrite + heavy-path retirement.
- Ruff clean on every touched file; mypy strict clean on `swebench_matrix.py`.
- All existing SWE-bench cells-JSONL row fields preserved verbatim (arm, role, case_id, trial, verdict, reason, passed, source, detail, elapsed_ms, root, config_fp, run_id, prompt_tokens, completion_tokens, inference_ms, model_calls, estimated, reproduction, recall_at_k, full_recall_at_k). A pre-Sprint-199b cells file resumes cleanly under the rewrite (foreign-config guard unchanged).
- New `SWEBENCH_ARMS=solve_and_grade` mode wires Sprint 197's `swebench_solve_and_grade_arm` + `swebench_solve_and_grade_suite` as the log-projection path; `matrix` keeps the record oracle for container-arm compat.
- Heavy topology `swebench_solver_topology_with_test_selection` still exists under `_deprecated/` and still fires from `swebench_solver_arm` (a separate follow-on). No matrix-arm code path reaches it.

## what remains after S7b

- **`swebench_solver_arm` migration.** The pre-Sprint-197 arm still builds via `solver_topology_from_payload` → `swebench_solver_topology_with_test_selection` (the heavy path). A separate sprint should migrate `SWEBENCH_ARMS=solver` to `swebench_repair_arm` at n=N, retiring the last live caller of the heavy path.
- **`container_arm` grade-producer.** For a full matrix under `swebench_log_projection_oracle`, `container_arm` needs its own grade producer emitting `GradeResult`. Once done, `SWEBENCH_ARMS=solve_and_grade` can carry the container arm; today it omits it.
- **S9 wire-check at N=300 Lite** and **S10 Verified pass 1.** Real behavioral runs against Docker + Ollama — both live on this box. The observation contract for the runner rewrite fires there.

## roadmap position

S0–S6 landed with the live consumer path (Sprint 197). S8 landed (Sprint 198). S7a landed (Sprint 199 — extraction). S7a-SDD-fold landed (Sprint 199a — CellSource canonical home + typed budget_exceeded field). S7b lands here. Next: S9 wire-check at N=300 Lite.
