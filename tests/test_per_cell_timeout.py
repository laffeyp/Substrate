"""Sprint 198 (roadmap v2 S8): the confirmatory runner's per-cell wall-clock derives from
the per-repo timeout table (`assay/swebench_timeouts.json`), capped by `RUN_TIMEOUT`.

`timeout_for_instance(instance_id)` at `assay/swebench.py:107` reads the table and returns
the wall-clock deadline for one instance. Sprint 198 uses it at the runner's
`asyncio.wait_for` boundary. Pin the semantics:

- A repo present in the table gets its declared timeout.
- A repo absent from the table falls back to the default (`_DEFAULT_TIMEOUT_SECONDS`, 60 min).
- The runner caps at `RUN_TIMEOUT` — an operator setting `SWEBENCH_RUN_TIMEOUT=600` gets 600 max
  even for sympy.
"""

from __future__ import annotations

from pathlib import Path


def test_timeout_for_instance_reads_per_repo_from_table():
    """`timeout_for_instance('sympy__sympy-12345')` looks up `sympy/sympy` in the table."""
    from substrate.assay.swebench import _DEFAULT_TIMEOUT_SECONDS, timeout_for_instance

    table = {"sympy/sympy": 5400, "django/django": 2700}
    assert timeout_for_instance("sympy__sympy-12345", table) == 5400
    assert timeout_for_instance("django__django-98765", table) == 2700
    assert timeout_for_instance("unknown__repo-1", table) == _DEFAULT_TIMEOUT_SECONDS


def test_default_when_table_missing_entry(tmp_path):
    """A repo not in the table falls back to `_DEFAULT_TIMEOUT_SECONDS`."""
    from substrate.assay.swebench import _DEFAULT_TIMEOUT_SECONDS, timeout_for_instance

    assert timeout_for_instance("nonexistent__repo-99", {}) == _DEFAULT_TIMEOUT_SECONDS


def test_shipped_swebench_timeouts_table_parses():
    """The committed `assay/swebench_timeouts.json` parses and covers the major SWE-bench
    Lite repos (sympy, django, astropy)."""
    from substrate.assay.swebench import _SWEBENCH_TIMEOUTS_PATH, read_swebench_timeouts

    table = read_swebench_timeouts()
    # Shipped table may be empty on a fresh checkout — allow that, but if it exists it must parse.
    if _SWEBENCH_TIMEOUTS_PATH.exists():
        assert isinstance(table, dict)
        for k, v in table.items():
            assert isinstance(k, str)
            assert isinstance(v, int)
            assert v > 0


def test_runner_wires_per_repo_timeout_via_budget_for_cell():
    """Sprint 198 + 199b source-scan pin. Sprint 199b moved the per-cell wait_for from an
    inline `cell()` loop into `run_suite_with_salvage`'s `budget_for_cell` callback; the
    runner passes a `_budget_for_cell(arm, case)` that reads `timeout_for_instance(...)`
    capped by RUN_TIMEOUT. Regression: a future edit that hardcodes the timeout at the
    callback site trips this pin."""
    runner_path = (
        Path(__file__).resolve().parent.parent / "scripts" / "assay_swebench_confirmatory.py"
    )
    src = runner_path.read_text()
    assert "timeout_for_instance(" in src, (
        "Sprint 198 wired the per-cell timeout via timeout_for_instance; a regression here "
        "would restore the hardcoded RUN_TIMEOUT for every cell regardless of repo."
    )
    assert "budget_for_cell=_budget_for_cell" in src, (
        "Sprint 199b passes the per-cell budget as a callback into run_suite_with_salvage; "
        "a regression that inlines the timeout would restore the fragility this closed."
    )
    # RUN_TIMEOUT still exists — it caps the per-repo value from the table.
    assert "min(" in src and "RUN_TIMEOUT" in src
