"""The assay control plane + control-ran guard + paired Report — Sprints 3 & 4.

End-to-end and deterministic, no network: two Arms (a baseline that always answers "20" and a full
Arm that answers each Case's ground truth) run over two Cases through `run_suite`, and `build_report`
produces the paired comparison. The arms emit a ModelUsage (via the metered seam, with a deterministic
stand-in) so the per-dimension usage aggregation is exercised too. The conformance guard's three states
and the delta-gating (no control -> no delta number) are tested directly.
"""

import pytest
from msgspec import Struct

from substrate import api
from substrate.assay import (
    BASELINE,
    FAIL,
    FULL,
    NO_CONTROL,
    PASS,
    Arm,
    Case,
    LogProjectionOracle,
    Suite,
    build_report,
    check_control_ran,
    exact_mcnemar_p,
    run_suite,
)
from substrate.reference._models import DeterministicResponder, call_responder_metered


class _Final(Struct, frozen=True):
    text: str


def _answer_topology(answer: str):
    """A one-Producer topology that emits a ModelUsage (a metered stand-in call, for the usage
    aggregation) and then a _Final carrying a CONTROLLED answer string (so pass/fail is deterministic)."""
    responder = DeterministicResponder(seed=0)

    def _factory():
        async def producer(_inp):
            _text, usage = await call_responder_metered(responder, "decide")
            yield usage
            yield _Final(text=answer)

        return lambda: producer

    def topo(b: api.TopologyBuilder) -> None:
        from substrate.reference._models import ModelUsage

        b.producer_kind(
            "answerer",
            schemas=[ModelUsage, _Final],
            schema_version=1,
            factory=_factory(),
            deterministic=True,
        )
        b.initial("answerer", input=None)
        b.termination(api.all_completed())

    return topo


def _final_text(envelopes):
    finals = [e for e in envelopes if e["kind"] == "_Final"]
    return finals[-1]["payload"]["text"] if finals else None


def _suite() -> Suite:
    return Suite(
        name="demo",
        version="0.1",
        cases=(Case("a", {}, "20"), Case("b", {}, "30")),
        arms=(
            Arm(name="baseline", role=BASELINE, build=lambda case: _answer_topology("20")),
            Arm(
                name="full", role=FULL, build=lambda case: _answer_topology(str(case.ground_truth))
            ),
        ),
        oracle=LogProjectionOracle(extract=_final_text, metric="exact_match"),
        control_arm="baseline",
        primary_metric="exact_match",
        null_rule="report NULL if the primary-endpoint 95% CI crosses zero at the trial budget",
    )


async def test_run_suite_and_paired_report(tmp_path):
    suite = _suite()
    results = await run_suite(suite, tmp_path, trials=1)
    assert len(results) == 4  # 2 arms x 2 cases x 1 trial
    report = build_report(suite, results)

    assert report.control_check.state == PASS
    by_name = {a.arm: a for a in report.arms}

    base = by_name["baseline"]
    assert base.pass_rate == 0.5  # answers "20": passes case a, fails case b
    assert base.delta_vs_control is None  # the control has no delta against itself

    full = by_name["full"]
    assert full.pass_rate == 1.0  # answers each case's ground truth: passes both
    assert full.delta_vs_control == 0.5  # 1.0 - 0.5
    # discordant: on case b the control fails and full passes (c=1); none the other way (b=0).
    assert full.discordant_control_only == 0
    assert full.discordant_arm_only == 1
    assert full.p_value == 1.0  # one discordant pair proves nothing — honestly underpowered

    # per-dimension usage: each arm ran 2 cases, one metered (stand-in) call each.
    assert full.model_calls == 2
    assert full.completion_tokens == 2  # the stub answer is one token per call
    assert full.estimated_usage is True  # stand-in usage, marked as such


async def test_delta_is_gated_when_control_did_not_run(tmp_path):
    # drop the control arm's results: build_report must refuse every delta (no control, no number).
    suite = _suite()
    results = await run_suite(suite, tmp_path, trials=1)
    without_control = [r for r in results if r.arm != "baseline"]
    report = build_report(suite, without_control)
    assert report.control_check.state == NO_CONTROL
    for arm in report.arms:
        assert arm.delta_vs_control is None
        assert arm.p_value is None


async def test_control_ran_check_three_states(tmp_path):
    suite = _suite()
    results = await run_suite(suite, tmp_path, trials=1)

    # PASS: the control ran on every case.
    assert check_control_ran(results, suite).state == PASS

    # FAIL: the control ran on some but not all cases (drop one control case).
    partial = [r for r in results if not (r.arm == "baseline" and r.case_id == "b")]
    fail = check_control_ran(partial, suite)
    assert fail.state == FAIL and "missing" in fail.detail

    # NO_CONTROL: the control produced no results at all.
    none_control = [r for r in results if r.arm != "baseline"]
    assert check_control_ran(none_control, suite).state == NO_CONTROL


def test_exact_mcnemar_p():
    assert exact_mcnemar_p(0, 0) == 1.0  # no discordant pairs -> no evidence
    assert exact_mcnemar_p(5, 5) == 1.0  # symmetric -> no signal
    # 8 vs 0: strongly one-sided. exact two-sided p = 2 * (1/2)^8 = 1/128.
    assert exact_mcnemar_p(8, 0) == pytest.approx(2 / 256)
    assert exact_mcnemar_p(8, 0) < 0.01


def test_suite_validation():
    case = Case("a", {}, "x")
    arm = Arm(name="only", role=BASELINE, build=lambda c: _answer_topology("x"))
    # control_arm must name a real arm
    with pytest.raises(ValueError):
        Suite(
            "s", "0.1", (case,), (arm,), LogProjectionOracle(extract=_final_text), "nope", "m", "n"
        )
    # empty cases
    with pytest.raises(ValueError):
        Suite("s", "0.1", (), (arm,), LogProjectionOracle(extract=_final_text), "only", "m", "n")
    # bad arm role
    with pytest.raises(ValueError):
        Arm(name="x", role="not-a-role", build=lambda c: _answer_topology("x"))
    # collision/path guards: '__' is the run-root separator, '/' would traverse — both rejected so two
    # (arm, case) pairs can never share a root.
    with pytest.raises(ValueError):
        Arm(name="a__b", role=BASELINE, build=lambda c: _answer_topology("x"))
    with pytest.raises(ValueError):
        Suite(
            "s",
            "0.1",
            (Case("a/b", {}, "x"),),
            (arm,),
            LogProjectionOracle(extract=_final_text),
            "only",
            "m",
            "n",
        )
