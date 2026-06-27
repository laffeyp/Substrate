"""Observation contract for the SELECT test-exec seam (sprint 140). The parsers are pure units; the
validate factory is exercised with a STAND-IN TestRunner (the real Docker runner is the gate-#3
integration). TestResults is the observable."""

from typing import Any

from substrate.topologies.swebench_solver.records import Reproduction
from substrate.topologies.swebench_solver.select_exec import (
    parse_test_outcomes,
    passed_tests,
    regression_held,
    regression_passed,
    reproduction_status,
    select_exec_validate_factory,
)

# a realistic pytest -rA summary tail: some pass, some fail (one is a pre-existing/env failure).
_RA_OUTPUT = """\
PASSED tests/test_json.py::test_dump
PASSED tests/test_json.py::test_load
FAILED tests/test_views.py::test_deprecated - DeprecationWarning
ERROR tests/test_cli.py::test_x
======= 2 passed, 1 failed, 1 error =======
"""


def test_parse_test_outcomes_and_passed() -> None:
    outcomes = parse_test_outcomes(_RA_OUTPUT)
    assert outcomes["tests/test_json.py::test_dump"] == "passed"
    assert outcomes["tests/test_views.py::test_deprecated"] == "failed"
    assert outcomes["tests/test_cli.py::test_x"] == "error"
    assert passed_tests(_RA_OUTPUT) == {"tests/test_json.py::test_dump", "tests/test_json.py::test_load"}


def test_regression_held_charges_only_new_failures() -> None:
    base = passed_tests(_RA_OUTPUT)  # the two test_json tests
    # patched run: a base-passing test still passes, and a test that FAILED at base still fails (env noise) ->
    # held (the pre-existing failure is not charged to the candidate).
    patched_ok = "PASSED tests/test_json.py::test_dump\nFAILED tests/test_views.py::test_deprecated - x\n"
    assert regression_held(base, patched_ok) is True
    # patched run where a base-PASSING test now fails -> a real regression -> not held.
    patched_bad = "FAILED tests/test_json.py::test_dump - broke\n"
    assert regression_held(base, patched_bad) is False
    # nothing from the base-passing set ran (collection broke) -> no positive evidence -> not held.
    assert regression_held(base, "ERROR tests/test_other.py::test_z\n") is False


def test_regression_passed_requires_positive_evidence() -> None:
    assert regression_passed(0, "3 passed in 0.1s") is True
    assert regression_passed(1, "3 passed") is False  # non-zero exit
    assert regression_passed(0, "1 failed, 2 passed") is False  # a failure
    assert regression_passed(0, "1 error") is False  # an error
    assert regression_passed(0, "no tests ran") is False  # no positive evidence (exit-gaming)


def test_reproduction_status_parses_markers() -> None:
    assert reproduction_status("...\nIssue resolved\n") == Reproduction.RESOLVED
    assert reproduction_status("Issue reproduced") == Reproduction.REPRODUCED
    assert reproduction_status("traceback ...") == Reproduction.OTHER


class _StubRunner:
    """A stand-in TestRunner: returns canned (returncode, output) per test command, no Docker."""

    def __init__(self, outcomes: dict[str, tuple[int, str]]) -> None:
        self._outcomes = outcomes

    def run(self, model_patch: str, test_command: str, extra_files: dict[str, str] | None = None) -> tuple[int, str]:
        return self._outcomes[test_command]


async def test_select_exec_emits_test_results() -> None:
    # the reproduction test runs as "python /sol/repro.py" (the generated code goes in via extra_files).
    runner = _StubRunner({"REG": (0, "3 passed in 0.1s"), "python /sol/repro.py": (0, "Issue resolved")})
    validate = select_exec_validate_factory(runner, "REG", repro_code="print('Issue resolved')")()
    results = [r async for r in validate({"slot": 2, "model_patch": "diff"})]
    assert len(results) == 1
    tr = results[0]
    assert tr.slot == 2 and tr.regression_passed is True and tr.reproduction == Reproduction.RESOLVED


async def test_select_exec_no_reproduction() -> None:
    runner = _StubRunner({"REG": (1, "1 failed")})
    validate = select_exec_validate_factory(runner, "REG", repro_code="")()  # no reproduction test
    results: list[Any] = [r async for r in validate({"slot": 0, "model_patch": "diff"})]
    assert results[0].regression_passed is False and results[0].reproduction == Reproduction.OTHER
