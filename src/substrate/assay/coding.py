"""The firewalled coding benchmark — the legible first measurement (review cracks 1, 2, 6).

A topology winning on a coding benchmark is the thing people already understand; this builds it to a
standard that survives scrutiny. Two corrections from the methodology review are structural here:

  - CRACK 1 — the FIREWALL. coding_flow's correction loop is fed the gate's failures, so if the gate
    the agent iterates on shares tests with the oracle that grades it, the loop is taught to the test
    and a "win" is leakage. So a CodingProblem carries TWO disjoint test sets: the DEV tests (the
    agent's gate — what it sees and iterates against) and the HELD-OUT grading tests (what the
    `coding_oracle` scores on, never shown to the agent). The candidate cannot overwrite the held-out
    tests either (fixtures win on key collision, both in the gate and here).
  - CRACK 2 — ATTRIBUTE the win to the MECHANISM, not "more attempts." The arm matrix is an ablation
    ladder: a single weak model, the weak ENSEMBLE without correction, and the full ensemble + the
    correction loop — each a delta against the control, so a gain is pinned to the specific structure.
  - CRACK 6 — the control is the STRONG single model (the bar to erode). The headline question is the
    TOST equivalence verdict on `full`: does orchestration around weak/free models reach the strong
    model? "equivalent" = the erosion the whole project is aiming at, measured rather than asserted.

The oracle is an external-grader (it runs the held-out tests in a sandbox), so it is run-and-observe,
NOT replayable, and a deterministic grader is not a valid one — partial/leaky tests still mis-score
(SWE-Bench+; crack 5). `coding_oracle` reports the held-out verdict per Case; grader-validity (residual
oracle error) is a follow-up axis, not claimed away as "ground truth".
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from msgspec import Struct

from ..topologies.coding_flow import coding_flow_topology, walkthrough_responders
from ..topologies.coding_flow.gate import (
    parse_artifacts,
    run_gate,
    sanitize_candidate_artifacts,
)
from ..topologies.coding_flow.task import CodingTask
from .oracle import ExternalGraderOracle
from .suite import ABLATION, BASELINE, FULL, Arm, Case, Suite


class CodingProblem(Struct, frozen=True):
    """One coding problem with a FIREWALL between what the agent sees and what it is graded on.

    `spec` instructs the drafters. `dev_gate` + `dev_fixtures` are the gate the agent's correction loop
    iterates against (its visible tests). `grading_command` + `grading_tests` are the HELD-OUT set the
    oracle scores on — they MUST be disjoint from the dev tests, or the firewall is a no-op and a win is
    leakage. Both sets pass through the same ruff/mypy/pytest shape; only the test files differ."""

    problem_id: str
    spec: str
    dev_gate: str
    dev_fixtures: dict[str, str]
    grading_command: str
    grading_tests: dict[str, str]


def _selected_candidate_response(record: Sequence[Mapping[str, Any]]) -> str | None:
    """The response coding_flow SELECTED: the Candidate at the (round, slot) the Solved event names. If
    the run Exhausted (no candidate passed the dev gate), there is no selected solution -> None."""
    solved = [e for e in record if e["kind"] == "Solved"]
    if not solved:
        return None
    rnd = int(solved[0]["payload"]["round"])
    slot = int(solved[0]["payload"]["slot"])
    for e in record:
        if (
            e["kind"] == "Candidate"
            and int(e["payload"]["round"]) == rnd
            and int(e["payload"]["slot"]) == slot
        ):
            return str(e["payload"]["response"])
    return None


def coding_oracle(*, timeout: float = 120.0) -> ExternalGraderOracle:
    """An external-grader Oracle that grades coding_flow's SELECTED candidate against the Case's
    HELD-OUT tests (the firewall). `ground_truth` is the CodingProblem (so the held-out tests ride
    per-Case). A run that Exhausted, or whose selected candidate cannot be found, grades not-resolved
    with a note — never a crash. Run-and-observe (replayable=False)."""

    def grader(record: list[Mapping[str, Any]], ground_truth: Any) -> tuple[bool, str]:
        problem: CodingProblem = ground_truth
        response = _selected_candidate_response(record)
        if response is None:
            return (False, "no candidate passed the dev gate (Exhausted) — no solution to grade")
        # sanitize the candidate (drop injected config/test files), THEN the held-out tests WIN on
        # collision: a candidate can neither overwrite the grading test nor inject a conftest/pyproject
        # whose addopts fakes a collect-only pass (firewall grade-time isolation, review fold).
        artifacts = {
            **sanitize_candidate_artifacts(parse_artifacts(response)),
            **problem.grading_tests,
        }
        result = run_gate(artifacts, problem.grading_command, timeout=timeout)
        # exit code 0 ALONE is forgeable: a candidate can `os._exit(0)` (or sys.exit(0)) at import to make
        # the gate process exit clean WITHOUT the held-out tests ever running. Require POSITIVE evidence —
        # pytest reported the expected number of held-out tests passed (a gamed exit prints no summary).
        expected = sum(t.count("def test_") for t in problem.grading_tests.values())
        resolved = result.passed and _held_out_actually_passed(result.summary, expected)
        return (
            resolved,
            f"held-out grade: {'resolved' if resolved else 'not resolved'} (rc={result.returncode}; "
            f"need >= {expected} held-out tests reported passed)",
        )

    return ExternalGraderOracle(grader=grader, metric="resolved")


_PASSED_RE = re.compile(r"(\d+)\s+passed")


def _held_out_actually_passed(summary: str, expected: int) -> bool:
    """POSITIVE-evidence check on the gate output: pytest must report at least `expected` tests passed,
    with no failures or errors. Defeats exit-code gaming (an `os._exit(0)` at import exits clean but
    prints no 'N passed' line) — a clean exit is necessary but not sufficient for 'resolved'."""
    low = summary.lower()
    if expected <= 0 or " failed" in low or " error" in low:
        return False
    m = _PASSED_RE.search(summary)
    return m is not None and int(m.group(1)) >= expected


def _task(problem: CodingProblem) -> CodingTask:
    """coding_flow's CodingTask built from the problem's DEV side only — the agent never sees the
    held-out grading tests (they live only in the oracle)."""
    return CodingTask(
        name=problem.problem_id,
        spec=problem.spec,
        gate=problem.dev_gate,
        fixtures=problem.dev_fixtures,
        ci_good="",
        ci_bad="",
    )


def coding_suite(
    problems: Sequence[CodingProblem],
    *,
    strong_model: str,
    weak_models: Sequence[str],
    equivalence_margin: float = 0.1,
    pass_k: int = 1,
    max_rounds: int = 2,
) -> Suite:
    """Build the firewalled coding A/B. CONTROL = `strong_ref` (the strong single model, the bar to
    erode). Arms ablate the structure over the weak/free `weak_models`: a single weak model, the weak
    ensemble without correction, and the full ensemble + correction loop. Each arm's delta is vs the
    strong control; the headline is the TOST equivalence verdict on `full` (does free orchestration
    reach the strong model). The oracle grades on the HELD-OUT tests (firewall)."""
    if not weak_models:
        raise ValueError("coding_suite needs at least one weak model")
    weak = list(weak_models)
    n = len(weak)

    def build(models: list[str], k: int, rounds: int) -> Any:
        def b(case: Case) -> Any:
            return coding_flow_topology(
                _task(case.ground_truth),
                responders=walkthrough_responders(models),
                n=k,
                max_rounds=rounds,
            )

        return b

    cases = tuple(Case(case_id=p.problem_id, payload={}, ground_truth=p) for p in problems)
    arms = (
        Arm(
            "strong_ref", build([strong_model], 1, 1), role=BASELINE
        ),  # the control: the bar to erode
        Arm(
            "weak_single", build([weak[0]], 1, 1), role=ABLATION
        ),  # a single weak model (the floor)
        Arm(
            "ensemble_no_correction", build(weak, n, 1), role=ABLATION
        ),  # ensemble diversity, no loop
        Arm(
            "full", build(weak, n, max_rounds), role=FULL
        ),  # ensemble + correction — reaches the bar?
    )
    return Suite(
        name="coding-firewalled",
        version="0.1",
        cases=cases,
        arms=arms,
        oracle=coding_oracle(),
        control_arm="strong_ref",
        primary_metric="resolved-held-out",
        null_rule=(
            "the headline is the TOST verdict on `full` vs the strong control: `equivalent` (CI inside "
            "±margin) means free orchestration reached the strong model; `inferior` means a real gap "
            "remains; non-significance alone is never read as either."
        ),
        equivalence_margin=equivalence_margin,
        pass_k=pass_k,
    )
