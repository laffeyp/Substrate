# Deprecated SWE-bench solver code

## Retired 2026-08-11 — `swebench_solver_topology_with_test_selection`

**Last live at HEAD post-Move-4 (commit that lands this README); post-Move-2 sha
`7359439` was the last commit before deprecation warned at build time.**

**What retired.** `swebench_solver_topology_with_test_selection` at
`src/substrate/topologies/swebench_solver/assemble.py:438`. It wired the heavy
"solve → test → rerank" apparatus — `select_exec`, `select_docker`,
`select_regression`, `repro_base_validate`, `reproduction` — that ran pytest
inside the eval image against each candidate patch and reranked by test
outcomes before emitting `SelectedPatch`.

**Why retired.** Postmortem `docs/POSTMORTEM-2026-08-10-swebench-topology-drift.md`
recorded RC1 in one sentence: the topology grew a duplicate of the grader. Every
cell ran up to eight Docker containers where the June 27 shape ran one. The
harness graded the emitted patch anyway; the in-topology test execution was
work the harness would repeat. On the 2026-08-10 Verified pass-1 attempt, 517
of 854 patches (60%) got no harness report — every one timed out inside the
in-topology test-selection container long before the harness could ask about
them. Those 517 got charged as `resolved=false` because the topology's silence
was rolled into the wrong bucket. The design v3 revert (2026-08-10) confirmed
the fix: use `swebench_repair_topology` (localize → best-of-N repair → emit the
first patch that applied), let the harness grade. The 2026-08-11 wire-check at
N=300 Lite through the light topology confirmed the shape holds under 1500
cells with zero orphan containers.

**Why not deleted.** Two live callers still use the heavy path — `scripts/solve_instance.py`
and `scripts/flask_solve.py` — as historical single-instance demonstrations.
`_build_solver_arm_from_payload(..., include_test_selection=True)` also keeps
the escape hatch open for a study caller. Deletion needs to untangle
`_select_exec_factory`, `_selector_factory`, `_solved_round`, `_round_verdicts`,
`_build_edit_context`, and the five `_VIEW_*` constants from `assemble.py`
without breaking `swebench_repair_topology`, which shares the same file.

**Revival path.** Any refactor that would route matrix arms back through this
topology must first commit a sprint that measures the delta between
in-topology test selection and harness-only grading on the same N=300 Lite set,
and reports the resolve-rate + wall-clock trade honestly. Without that
measurement, in-topology selection is engineering debt dressed as optionality —
the exact shape RC1 recorded.

**Runtime signal.** The function warns via `DeprecationWarning` when built;
`_build_solver_arm_from_payload` also warns when a caller opts in with
`include_test_selection=True`. A test suite that runs with
`filterwarnings = ["error::DeprecationWarning"]` fails loudly on any new
consumer.
