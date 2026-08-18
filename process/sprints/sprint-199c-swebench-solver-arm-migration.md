# Sprint 199c — `swebench_solver_arm` migrated off the heavy topology (roadmap v2 S7b close)

Sprint 199b retired the `include_test_selection=True` opt-in on the matrix-arm factory. `swebench_solver_arm` (the pre-Sprint-197 arm still used by `SWEBENCH_ARMS=solver` mode and by `scripts/assay_swebench_run.py`) remained on the heavy path via `solver_topology_from_payload` → `swebench_solver_topology_with_test_selection`. Sprint 199c closes that last live production caller.

## files touched

- `src/substrate/assay/swebench_suite.py` — `solver_topology_from_payload` rewritten to build `swebench_repair_topology` (light) instead of `swebench_solver_topology_with_test_selection` (heavy). `repro_k` kept in the signature for source-compat with pre-migration callers, unused. Dropped the `DockerTestRunner` + `make_regression_planner` + `passed_at_base` wiring from the body — the light topology needs none of that in-topology because the harness grades. Removed unused imports: `swebench_solver_topology_with_test_selection`, `make_regression_planner`. `swebench_solver_arm` docstring updated to name the migration; its body is unchanged (still calls `solver_topology_from_payload`, which now returns the light topology).
- `tests/test_assay_swebench_suite.py` — removed the per-file `pytest.mark.filterwarnings` that suppressed the heavy topology's DeprecationWarning; the migration removed the last library caller so the filter has no live use. Header comment updated.

## contracts

- 838 passed / 4 skipped in 322s on the full suite; net zero regressions.
- Ruff clean on every touched file; mypy strict clean on `swebench_suite.py`.
- `swebench_solver_arm` and `solver_topology_from_payload` API surfaces preserved verbatim — every existing caller (script, test, external) sees the same function names + parameter shapes.
- Behavior improves for `SWEBENCH_ARMS=solver` runs: the arm no longer wires `select_exec` (in-topology test execution) or the reproduction planner. The harness alone grades. This closes the shape that produced the 517-silent-fails failure mode documented in the 2026-08-10 postmortem.
- **Observation contract:** fired the migrated runner end-to-end against 1 Lite instance (astropy-12907) with `SWEBENCH_ARMS=solver`, llama3.2:1b. 14 seconds wall. 3 real Ollama calls (2525 prompt / 486 completion). RepoClone typed events on stderr; no in-topology container events (select_exec retired). Cells JSONL row lands with every field intact and matches the Sprint 199b smoke's shape. Pre-migration comparison: Sprint 199b's identical smoke fired 4 model calls in 9s because the heavy topology sampled a reproduction script alongside the drafters — the migrated path produces one fewer call for the same drafter count, evidence the retired producers are gone.

## remaining callers of the deprecated heavy topology (all documented, non-production)

- `scripts/solve_instance.py` — EXPLORATORY single-instance runner. Uses the heavy topology deliberately to observe in-topology test selection. Never in the confirmatory path.
- `scripts/flask_solve.py` — Stage 1 gold-fed verification. Same rationale.
- `tests/test_swebench_solver.py` — the deprecated topology's own regression tests. Per-file `filterwarnings` suppresses the DeprecationWarning.

The heavy topology `swebench_solver_topology_with_test_selection` lives on at `src/substrate/topologies/swebench_solver/assemble.py` with its DeprecationWarning intact. No library path or confirmatory arm reaches it; only the three above call sites remain, each with a documented reason.

## roadmap position

S0–S6 landed with the live consumer path (Sprint 197). S8 landed (Sprint 198). S7a landed (Sprint 199 — extraction of `run_suite_with_salvage`). S7a-SDD-fold landed (Sprint 199a — `CellSource` canonical home + typed `budget_exceeded` field). S7b landed (Sprint 199b — runner rewrite around `run_suite_with_salvage`; matrix-arm `include_test_selection` retired). S7b-close lands here (Sprint 199c — last library caller of the heavy topology migrated to the light path). Next: S9 wire-check at N=300 Lite; S10 Verified pass 1.
