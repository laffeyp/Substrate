# scripts/_deprecated/

Retired scripts kept per AGENTS.md hard rule 12: the audit trail is the work. Bodies preserved verbatim so any prior review or postmortem that cites them still resolves; the CI guard at `scripts/check_deprecated_preserved.sh` (Sprint 175) fails when a commit deletes a file under this directory.

## Retired

### `docker_runner_smoke.py` — retired Sprint 182 (2026-08-12)

Smoked `DockerTestRunner` against the live flask-4045 image (pull → apply gold patch → run blueprint tests → confirm regression holds). Imports `DockerTestRunner` and `regression_passed` from `topologies/swebench_solver/select_docker.py` and `.../select_exec.py` — both satellite modules of the retired heavy topology `swebench_solver_topology_with_test_selection`. Under the light-topology revert (design v3, ratified 2026-08-10), `DockerTestRunner` survives as the harness-side grade runner via `assay/swebench.py::run_swebench_one`; the standalone DockerTestRunner smoke is redundant with the harness-binding gold-differential test at `tests/test_assay_swebench_harness_binding.py::@pytest.mark.swebench_harness`.

Revival: if a future sprint needs a live-Docker smoke against a single instance without the swebench harness, this file's shape is the reference. Copy, do not edit in place.

### `regression_seam_smoke.py` — retired Sprint 182 (2026-08-12)

Smoked the regression-picker + `DockerTestRunner` + `regression_held` end to end on the live flask-4045 image. Every import (`select_docker`, `select_exec`, `select_regression`) reaches a satellite of the retired heavy topology. The regression-selection seam is not part of the light-topology grade path; smoking it validates infrastructure no confirmatory path exercises. Retire alongside the topology it served.

Revival: if a future sprint reinstates in-topology test-based selection (see `topologies/swebench_solver/_deprecated/README.md` for the topology-level revival path), this smoke lives here as the reference test.

---

Sprint 182 close-note also corrects Sprint 173's close-note count. Sprint 173 reported "three scripts still importing the heavy topology" — the accurate count as of 2026-08-12 was three direct imports (`flask_solve.py`, `solve_instance.py`, `assay_swebench_run.py`) plus two satellite imports (`docker_runner_smoke.py`, `regression_seam_smoke.py`) = five files reaching the retired topology's world. Round-2 review R6 flagged the discrepancy. This directory absorbs the two satellite-importing files; the three direct-import files remain in `scripts/` as legacy debug utilities awaiting a follow-on migration or retirement decision.
