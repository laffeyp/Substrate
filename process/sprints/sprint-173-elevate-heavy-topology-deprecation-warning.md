# Sprint 173 — Elevate the heavy topology's DeprecationWarning to CI error (fold external F9)

---

```yaml
---
id: 173
status: closed
phase: 1
pass_kind: functional
---
```

## scope

Close F9. The 2026-08-11 retirement of `swebench_solver_topology_with_test_selection` at KIT_DIARY 38 named the retire-in-place discipline: the topology stays alive with a `DeprecationWarning` so any new consumer trips a `filterwarnings = ["error::DeprecationWarning"]` gate. That gate had not been wired. Sprint 173 wires it, then migrates the three test files that legitimately construct the deprecated topology to opt-in per-site.

## files modified

- `pyproject.toml` — `[tool.pytest.ini_options].filterwarnings` gains `"error:swebench_solver_topology_with_test_selection is deprecated:DeprecationWarning"`. Filter matches by warning-message substring, so any caller anywhere in the tree escalates to `DeprecationWarning`-as-error. Every other DeprecationWarning stays a warning.
- `tests/test_swebench_solver.py` — module-level `pytestmark = pytest.mark.filterwarnings("ignore:...")` opts every test in the file out of the escalation. Every test here legitimately constructs the deprecated topology per its documented purpose (nine end-to-end observation-contract tests against the heavy-topology's producer sequence).
- `tests/test_assay_swebench_suite.py` — same module-level opt-in; two tests legitimately reach the topology through `solver_topology_from_payload`.
- `tests/test_assay_swebench_matrix.py:170` — the one matrix test that opts into the heavy topology (via `include_test_selection=True`, the escape hatch it verifies) wrapped in `pytest.warns(DeprecationWarning, match=...)`.

## contracts

- Full test suite: 789 pass, 3 skipped (the swebench-harness and realmodel gated tests). No new failures.
- Any future test that builds the heavy topology outside these three opt-in sites will trip the filter and fail CI. That is the enforcement KIT_DIARY 38 named.
- Scripts (`scripts/flask_solve.py`, `scripts/solve_instance.py`, `scripts/assay_swebench_run.py`) still import the deprecated topology; they run outside pytest so the filter does not affect them. Reviewer's F9 named these scripts for migration; deferred to a follow-on because the scripts are legacy debug utilities (not part of any confirmatory path) and the retire-in-place discipline is preserved by the CI gate. A follow-on sprint may move the scripts to `scripts/_deprecated/` under hard rule 12.

## done

Four files (one pyproject + three tests). Full green. Retirement gate is now enforced in CI.
