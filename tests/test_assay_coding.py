"""The firewalled coding benchmark — Sprint (review cracks 1, 2, 6). Deterministic: no models.

The oracle is tested directly against a constructed record. The firewall's whole point is that a
candidate which passes the DEV tests it iterated on can still FAIL the held-out tests it is graded on —
so an overfit / leaked "win" is caught. The grading subprocess (ruff/pytest) runs for real; no model
does.
"""

from substrate.assay.coding import CodingProblem, coding_oracle, coding_suite
from substrate.assay.oracle import EXTERNAL_GRADER

# DEV test the agent sees: f(1) == 2.  HELD-OUT test the oracle grades on: f(2) == 3.  Disjoint.
_PROBLEM = CodingProblem(
    problem_id="increment",
    spec="Write `def f(x: int) -> int` in m.py. Output `# path: m.py` then a fenced python block.",
    dev_gate="python -m pytest -q",
    dev_fixtures={
        "test_dev.py": "from m import f\n\n\ndef test_dev() -> None:\n    assert f(1) == 2\n"
    },
    grading_command="python -m pytest -q",
    grading_tests={
        "test_grade.py": "from m import f\n\n\ndef test_grade() -> None:\n    assert f(2) == 3\n"
    },
)


def _record(response: str, rnd: int = 1, slot: int = 0):
    return [
        {"kind": "Candidate", "payload": {"round": rnd, "slot": slot, "response": response}},
        {"kind": "Solved", "payload": {"round": rnd, "slot": slot}},
    ]


def _file(body: str) -> str:
    return f"# path: m.py\n```python\n{body}\n```\n"


def test_firewall_catches_an_overfit_candidate():
    # an overfit candidate: f returns the constant 2 — it PASSES the dev test (f(1)==2) but FAILS the
    # held-out test (f(2)==3). The firewall (grade on held-out) catches what teaching-to-the-test hides.
    oracle = coding_oracle()
    overfit = oracle.grade(_record(_file("def f(x: int) -> int:\n    return 2")), _PROBLEM)
    assert overfit.passed is False  # passed dev, FAILED held-out -> not resolved
    assert overfit.oracle_class == EXTERNAL_GRADER and overfit.replayable is False

    # a genuinely correct candidate passes the held-out test too.
    correct = oracle.grade(_record(_file("def f(x: int) -> int:\n    return x + 1")), _PROBLEM)
    assert correct.passed is True


def test_candidate_cannot_overwrite_the_held_out_tests():
    # the candidate emits m.py (overfit) AND tries to overwrite the grading test with a vacuous pass.
    # held-out tests WIN on collision, so the real test_grade.py runs and the overfit fails.
    sneaky = (
        "# path: m.py\n```python\ndef f(x: int) -> int:\n    return 2\n```\n"
        "# path: test_grade.py\n```python\ndef test_grade() -> None:\n    assert True\n```\n"
    )
    res = coding_oracle().grade(_record(sneaky), _PROBLEM)
    assert res.passed is False  # the held-out test ran, not the candidate's vacuous override


def test_exhausted_run_grades_not_resolved():
    # no Solved on the record (the agent never passed even its own dev gate) -> no solution to grade.
    res = coding_oracle().grade([{"kind": "Exhausted", "payload": {"rounds": 2}}], _PROBLEM)
    assert res.passed is False and "Exhausted" in res.detail


def test_coding_suite_control_is_the_strong_model_and_arms_ablate():
    suite = coding_suite(
        [_PROBLEM], strong_model="strong", weak_models=["w1", "w2"], equivalence_margin=0.15
    )
    # the control is the STRONG single model — the bar to erode (crack 6).
    assert suite.control_arm == "strong_ref"
    # the ablation ladder: single weak / weak ensemble no-correction / full ensemble + correction.
    assert {a.name for a in suite.arms} == {
        "strong_ref",
        "weak_single",
        "ensemble_no_correction",
        "full",
    }
    assert suite.equivalence_margin == 0.15
    # the held-out tests ride on the Case ground_truth (the firewall: the task the agent gets carries
    # only the dev fixtures).
    assert suite.cases[0].ground_truth.problem_id == "increment"
    assert "test_grade.py" in suite.cases[0].ground_truth.grading_tests
