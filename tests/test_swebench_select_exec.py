"""Observation contract for the SELECT test-exec seam (sprint 140). The parsers are pure units; the
validate factory is exercised with a STAND-IN TestRunner (the real Docker runner is the gate-#3
integration). TestResults is the observable."""

from typing import Any

from substrate.topologies.swebench_solver.records import Reproduction
from substrate.topologies.swebench_solver.select_exec import (
    regression_passed,
    reproduction_status,
    select_exec_validate_factory,
)


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

    def run(self, model_patch: str, test_command: str) -> tuple[int, str]:
        return self._outcomes[test_command]


async def test_select_exec_emits_test_results() -> None:
    runner = _StubRunner({"REG": (0, "3 passed in 0.1s"), "REPRO": (0, "Issue resolved")})
    validate = select_exec_validate_factory(runner, "REG", "REPRO")()
    results = [r async for r in validate({"slot": 2, "model_patch": "diff"})]
    assert len(results) == 1
    tr = results[0]
    assert tr.slot == 2 and tr.regression_passed is True and tr.reproduction == Reproduction.RESOLVED


async def test_select_exec_no_reproduction_command() -> None:
    runner = _StubRunner({"REG": (1, "1 failed")})
    validate = select_exec_validate_factory(runner, "REG", None)()
    results: list[Any] = [r async for r in validate({"slot": 0, "model_patch": "diff"})]
    assert results[0].regression_passed is False and results[0].reproduction == Reproduction.OTHER
