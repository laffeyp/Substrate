"""The firewalled coding benchmark — Sprint (review cracks 1, 2, 6). Deterministic: no models.

The oracle is tested directly against a constructed record. The firewall's whole point is that a
candidate which passes the DEV tests it iterated on can still FAIL the held-out tests it is graded on —
so an overfit / leaked "win" is caught. The grading subprocess (ruff/pytest) runs for real; no model
does.
"""

from substrate.assay.coding import CodingProblem, coding_oracle, coding_suite
from substrate.assay.coding_problems import coding_problem_bank
from substrate.assay.oracle import EXTERNAL_GRADER
from substrate.topologies.coding_flow.gate import (
    parse_artifacts,
    run_gate,
    sanitize_candidate_artifacts,
)

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


def test_provenance_detects_a_tampered_margin():
    # the cargo-cult-via-sidecar attack: edit the recorded margin to a flattering value to manufacture a
    # verdict. The per-cell fingerprint (stamped at run time, in the append-only cell log) is the anchor;
    # editing the meta's margin without re-fingerprinting is DETECTED.
    import hashlib
    import json as _json

    from substrate.assay.cells import provenance_status

    cfg = {"strong_model": "s", "weak_models": ["w"], "trials": 10, "margin": 0.1}
    fp = hashlib.sha256(_json.dumps(cfg, sort_keys=True).encode()).hexdigest()[:12]
    meta = {"config_fp": fp, "run_id": "r1", **cfg}
    rows = [{"config_fp": fp}, {"config_fp": fp}]
    assert provenance_status(meta, rows) == "verified"
    assert provenance_status({**meta, "margin": 0.30}, rows) == "tampered"  # margin edited post-hoc
    assert provenance_status(meta, [{"config_fp": "deadbeef0000"}]) == "tampered"  # cells disagree
    assert provenance_status({}, [{"config_fp": None}]) == "unverified"  # pre-fingerprint run


def test_firewall_catches_exit_code_gaming():
    # an adversarial candidate defines f (wrong) then calls os._exit(0) at import — so when pytest
    # imports the module to run the held-out test, the process exits CLEAN (rc 0) before any test runs.
    # Exit-code 0 alone would read 'resolved'; the positive-evidence check (the held-out tests must
    # actually report passed) catches it.
    gamer = "# path: m.py\n```python\nimport os\n\n\ndef f(x: int) -> int:\n    return 2\n\n\nos._exit(0)\n```\n"
    assert coding_oracle().grade(_record(gamer), _PROBLEM).passed is False


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


# ── grade-time isolation (review #4) ──

_GATE_HARD = "python -m pytest -c /dev/null -q"


def test_sanitize_drops_config_and_test_files():
    # a candidate emits MODULES; config and test files are the harness's and are stripped before the
    # sandbox, so neither a neutering conftest/ini nor an injected test file ever runs.
    arts = {
        "rle.py": "x",
        "sub/mod.py": "y",
        "conftest.py": "x",
        "pytest.ini": "x",
        "pyproject.toml": "x",
        "tox.ini": "x",
        "test_evil.py": "x",
        "foo_test.py": "x",
    }
    assert set(sanitize_candidate_artifacts(arts)) == {"rle.py", "sub/mod.py"}


def test_firewall_isolation_blocks_config_injection():
    # the attack: an overfit module (f returns the dev-passing constant) PLUS a pytest.ini whose
    # addopts=--co would make pytest collect-only — exit 0, no test run, a FALSE 'resolved'. The
    # sanitizer drops the ini (and -c /dev/null ignores config), so test_grade actually runs and the
    # overfit is caught.
    problem = CodingProblem(
        problem_id="inc",
        spec="write f",
        dev_gate=_GATE_HARD,
        dev_fixtures={
            "test_dev.py": "from m import f\n\n\ndef test_dev() -> None:\n    assert f(1) == 2\n"
        },
        grading_command=_GATE_HARD,
        grading_tests={
            "test_grade.py": "from m import f\n\n\ndef test_grade() -> None:\n    assert f(2) == 3\n"
        },
    )
    sneaky = (
        "# path: m.py\n```python\ndef f(x: int) -> int:\n    return 2\n```\n"
        "# path: pytest.ini\n```ini\n[pytest]\naddopts = --co\n```\n"
    )
    record = [
        {"kind": "Candidate", "payload": {"round": 1, "slot": 0, "response": sneaky}},
        {"kind": "Solved", "payload": {"round": 1, "slot": 0}},
    ]
    assert coding_oracle().grade(record, problem).passed is False


def test_rotate_left_held_out_has_teeth():
    # the held-out used to be all identity rotations (k=0, k=len, empty), so `return xs` passed. With a
    # non-identity case added, the overfit now fails the held-out grade.
    p = next(x for x in coding_problem_bank() if x.problem_id == "rotate_left")
    overfit = "# path: rl.py\n```python\ndef rotate_left(xs: list[int], k: int) -> list[int]:\n    return xs\n```\n"
    arts = {**parse_artifacts(overfit), **p.grading_tests}
    assert run_gate(arts, p.grading_command).passed is False
