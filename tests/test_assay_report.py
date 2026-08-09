"""Repro-vs-oracle 2x2 + Cohen's kappa aggregation on ArmReport (sprint 158).

Pins the four cell counts, the raw agreement rate, and the chance-corrected kappa across the
edge cases that matter: the trusted repro (high kappa), the trivially-passing repro (high
raw agreement, kappa near zero — the exact false-positive that motivated the metric per
docs/swebench-solver-design.md §5), the "no signal" fallbacks, and the degenerate marginal
that makes kappa undefined.

Constructs `CaseResult`s directly so the test scope is the aggregation logic, not the
downstream reporting pipeline (which `test_assay_control_plane.py` and `test_assay_cells.py`
already cover end-to-end).
"""

from __future__ import annotations

import pytest

from substrate.assay.oracle import EXTERNAL_GRADER, Result
from substrate.assay.report import _repro_aggregate, build_report, exact_mcnemar_p
from substrate.assay.run import CaseResult, UsageTotals
from substrate.assay.suite import FULL, Arm, Case, Suite


def _cr(passed: bool, repro: str, arm: str = "solver", case_id: str = "c0") -> CaseResult:
    """A minimal CaseResult for the aggregation tests — usage/timing zeroed, oracle stubbed."""
    return CaseResult(
        arm=arm,
        role=FULL,
        case_id=case_id,
        trial=0,
        result=Result(
            passed=passed,
            score=1.0 if passed else 0.0,
            metric="resolved",
            oracle_class=EXTERNAL_GRADER,
            replayable=False,
        ),
        usage=UsageTotals(0, 0, 0, 0, False),
        elapsed_ms=0,
        root="",
        reproduction=repro,
    )


def test_repro_aggregate_perfect_agreement_yields_kappa_one():
    # Every RESOLVED matches a pass and every REPRODUCED matches a fail — the trusted-repro case.
    # a=3 (resolved+passed), b=0, c=0, d=2 (reproduced+failed) -> agreement = 1.0, kappa = 1.0.
    rows = [_cr(True, "resolved") for _ in range(3)] + [_cr(False, "reproduced") for _ in range(2)]
    twox2, kappa, agree = _repro_aggregate(rows)
    assert twox2 == {
        "resolved_and_passed": 3,
        "resolved_and_failed": 0,
        "reproduced_and_passed": 0,
        "reproduced_and_failed": 2,
    }
    assert agree == pytest.approx(1.0)
    assert kappa == pytest.approx(1.0)


def test_repro_aggregate_trivially_passing_repro_raw_agreement_collapses_to_oracle_rate():
    # The false-positive shape docs/swebench-solver-design.md §5 warns about: repro always says
    # RESOLVED. Oracle passes 8 of 10 cases; raw agreement COLLAPSES TO THE ORACLE'S PASS RATE
    # (0.8) — a spurious "high" number anchored to how often the oracle happened to pass. But
    # Cohen's kappa is EXACTLY ZERO: chance-corrected agreement collapses because one marginal
    # (repro) is degenerate at "always RESOLVED", so p_e = p_o = 0.8 and κ = 0. This is
    # precisely why raw agreement is NOT the number and κ is: a trivially-passing repro trips a
    # loud tell (κ ≈ 0) that raw agreement (0.8) HIDES.
    rows = [_cr(True, "resolved") for _ in range(8)] + [_cr(False, "resolved") for _ in range(2)]
    twox2, kappa, agree = _repro_aggregate(rows)
    assert twox2 == {
        "resolved_and_passed": 8,
        "resolved_and_failed": 2,
        "reproduced_and_passed": 0,
        "reproduced_and_failed": 0,
    }
    assert agree == pytest.approx(0.8)
    assert kappa == pytest.approx(0.0), (
        "trivially-passing repro: raw agreement is inflated by the base rate; "
        "kappa == 0 is the honest signal the metric is designed to expose"
    )


def test_repro_aggregate_undefined_kappa_on_both_marginals_collapsed():
    # BOTH marginals degenerate (every row is resolved+passed) -> p_o = 1.0, p_e = 1.0,
    # (1 - p_e) = 0 -> kappa is genuinely undefined (Cohen 1960 degenerate case). Returns None.
    # The 2x2 and raw agreement are still reported (agreement = 1.0) because those are defined.
    rows = [_cr(True, "resolved") for _ in range(5)]
    twox2, kappa, agree = _repro_aggregate(rows)
    assert twox2 == {
        "resolved_and_passed": 5,
        "resolved_and_failed": 0,
        "reproduced_and_passed": 0,
        "reproduced_and_failed": 0,
    }
    assert agree == pytest.approx(1.0)
    assert kappa is None


def test_repro_aggregate_all_disagreement_yields_negative_kappa():
    # Every RESOLVED aligns with a FAIL and every REPRODUCED aligns with a PASS — perfect
    # ANTI-agreement. n=4, a=0, b=2, c=2, d=0. p_o = 0. p_e = (2*2 + 2*2)/16 = 0.5. kappa = -1.
    rows = [_cr(False, "resolved") for _ in range(2)] + [_cr(True, "reproduced") for _ in range(2)]
    twox2, kappa, agree = _repro_aggregate(rows)
    assert twox2["resolved_and_failed"] == 2
    assert twox2["reproduced_and_passed"] == 2
    assert agree == pytest.approx(0.0)
    assert kappa == pytest.approx(-1.0)


def test_repro_aggregate_other_verdicts_excluded_from_twox2():
    # `other` (or empty, or an unrecognised string) is legitimately no-signal — excluded from
    # both the 2x2 counts and the marginals. Two REPRODUCED-FAIL + one OTHER row -> n=2 in the
    # 2x2, not 3.
    rows = [_cr(False, "reproduced"), _cr(False, "reproduced"), _cr(True, "other")]
    twox2, _kappa, _agree = _repro_aggregate(rows)
    assert twox2 is not None
    assert sum(twox2.values()) == 2


def test_repro_aggregate_returns_none_on_all_other_or_empty():
    # No signal at all -> all three returns are None. The ArmReport fields then stay None so a
    # downstream reader can distinguish "no repro data" from "signal was zero".
    rows = [_cr(True, "other"), _cr(False, ""), _cr(True, "")]
    twox2, kappa, agree = _repro_aggregate(rows)
    assert twox2 is None and kappa is None and agree is None


def test_repro_aggregate_returns_none_on_empty_input():
    # Zero cases in the arm -> None across the board. build_report never crashes on an empty arm.
    twox2, kappa, agree = _repro_aggregate([])
    assert twox2 is None and kappa is None and agree is None


def test_repro_aggregate_moderate_agreement_gives_moderate_kappa():
    # A non-trivial case: 4 RESOLVED+pass, 1 RESOLVED+fail, 1 REPRODUCED+pass, 4 REPRODUCED+fail.
    # n=10, agreement = 8/10 = 0.8. Marginals split 5/5 and 5/5. Cross-check by hand:
    # p_e = (5*5 + 5*5) / 100 = 0.5. kappa = (0.8 - 0.5) / (1 - 0.5) = 0.6.
    rows = (
        [_cr(True, "resolved") for _ in range(4)]
        + [_cr(False, "resolved")]
        + [_cr(True, "reproduced")]
        + [_cr(False, "reproduced") for _ in range(4)]
    )
    _twox2, kappa, agree = _repro_aggregate(rows)
    assert agree == pytest.approx(0.8)
    assert kappa == pytest.approx(0.6)


def test_repro_aggregate_excludes_non_canonical_case_as_drift():
    # Sprint 158 review F2: the wire form is ALWAYS lowercase (Reproduction.RESOLVED.value =
    # "resolved"). A row carrying "RESOLVED" or "Reproduced" was produced out-of-band — it is
    # vocabulary drift, not a typo the aggregator should paper over. The pre-fold version
    # `.lower()`-normalised these and silently included them, hiding a real signal (a wrong
    # writer emitting mis-cased enum values). This test pins the correct posture: exclude and
    # keep the 2x2 empty so an in-loop reader can notice the drift by seeing zero repro cells.
    rows = [_cr(True, "RESOLVED"), _cr(False, "Reproduced")]
    twox2, kappa, agree = _repro_aggregate(rows)
    assert twox2 is None
    assert kappa is None
    assert agree is None


def test_repro_aggregate_reads_realistic_record_dict_shape():
    # Sprint 158 review F1: `project_reproduction_for_selected` reads the record as a list of
    # {"kind", "payload"} dicts (what `api.read_record` yields — the on-disk JSON decoded
    # form). This test pins the projection against a hand-constructed record that mirrors what
    # the swebench_solver topology writes: a SelectedPatch pointing at slot=1 + two TestResults
    # (slot 0 and slot 1) with lowercase Reproduction.value strings (msgspec.to_builtins on the
    # enum produces the .value). Confirms the round-trip: enum -> to_builtins -> JSON -> dict
    # -> projection -> canonical lowercase string. Any change to the on-disk shape (an
    # accidental enum-as-str dump like "Reproduction.RESOLVED") would break this.
    from substrate.assay.run import project_reproduction_for_selected

    record = [
        {
            "kind": "SelectedPatch",
            "payload": {"slot": 1, "model_patch": "diff...", "reason": "regression"},
        },
        {
            "kind": "TestResults",
            "payload": {
                "slot": 0,
                "regression_passed": True,
                "reproduction": "reproduced",
                "summary": "",
            },
        },
        {
            "kind": "TestResults",
            "payload": {
                "slot": 1,
                "regression_passed": True,
                "reproduction": "resolved",
                "summary": "",
            },
        },
    ]
    assert project_reproduction_for_selected(record) == "resolved"

    # No SelectedPatch on the record -> no signal (empty), never a crash.
    assert project_reproduction_for_selected([]) == ""

    # SelectedPatch with a slot that has no matching TestResults -> empty.
    orphan = [
        {"kind": "SelectedPatch", "payload": {"slot": 3, "model_patch": "", "reason": ""}},
        {
            "kind": "TestResults",
            "payload": {
                "slot": 0,
                "regression_passed": False,
                "reproduction": "other",
                "summary": "",
            },
        },
    ]
    assert project_reproduction_for_selected(orphan) == ""

    # LAST TestResults with matching slot wins (max_rounds > 1 emits multiple; the terminal
    # verdict is what SELECT read to pick SelectedPatch, so it's what should land in the 2x2).
    multiround = [
        {"kind": "SelectedPatch", "payload": {"slot": 0, "model_patch": "", "reason": ""}},
        {
            "kind": "TestResults",
            "payload": {
                "slot": 0,
                "regression_passed": False,
                "reproduction": "reproduced",
                "summary": "",
            },
        },
        {
            "kind": "TestResults",
            "payload": {
                "slot": 0,
                "regression_passed": True,
                "reproduction": "resolved",
                "summary": "",
            },
        },
    ]
    assert project_reproduction_for_selected(multiround) == "resolved"


def test_build_report_carries_repro_fields_when_data_present():
    # End-to-end pin: `build_report` propagates the 2x2 + kappa + agreement onto ArmReport.
    # One arm, no control comparison to muddy the signal.
    arm = Arm(name="solver", role=FULL, build=lambda _c: None)  # type: ignore[arg-type,return-value]
    suite = Suite(
        name="s",
        version="0.1",
        cases=(Case(case_id="c0", payload={}, ground_truth=None),),
        arms=(arm,),
        oracle=type("O", (), {"grade": lambda self, _r, _g: None})(),  # unused by build_report
        control_arm="solver",
        primary_metric="resolved",
        null_rule="",
    )
    results = [
        _cr(True, "resolved", case_id="c0"),
        _cr(False, "reproduced", case_id="c0"),
    ]
    report = build_report(suite, results)
    (line,) = report.arms
    assert line.repro_2x2 == {
        "resolved_and_passed": 1,
        "resolved_and_failed": 0,
        "reproduced_and_passed": 0,
        "reproduced_and_failed": 1,
    }
    assert line.repro_kappa == pytest.approx(1.0)
    assert line.repro_agreement_rate == pytest.approx(1.0)


def test_build_report_repro_fields_stay_none_on_coding_style_data():
    # A coding assay: no `reproduction` field on any CaseResult (default ""). The ArmReport's
    # repro_* fields stay None — coding readers see no phantom zeros in the number.
    arm = Arm(name="solver", role=FULL, build=lambda _c: None)  # type: ignore[arg-type,return-value]
    suite = Suite(
        name="s",
        version="0.1",
        cases=(Case(case_id="c0", payload={}, ground_truth=None),),
        arms=(arm,),
        oracle=type("O", (), {"grade": lambda self, _r, _g: None})(),
        control_arm="solver",
        primary_metric="resolved",
        null_rule="",
    )
    results = [_cr(True, ""), _cr(False, "")]  # no repro column
    report = build_report(suite, results)
    (line,) = report.arms
    assert line.repro_2x2 is None
    assert line.repro_kappa is None
    assert line.repro_agreement_rate is None


def test_build_report_repro_fields_survive_the_paired_comparison_branch():
    # Sprint 158 review F4: the single-arm end-to-end test exercised only the control-arm
    # branch of build_report (which SKIPS McNemar + bootstrap), so it never proved the repro
    # fields survive the paired-comparison path. This test uses two arms (control + candidate)
    # both carrying repro data — verifies neither arm's repro_2x2/kappa/agreement is clobbered
    # when delta/CI/verdict computation runs alongside the aggregation.
    #
    # Uses the same _has_committed_record monkeypatch trick as test_assay_cells.py — the point
    # of this test is the aggregation path through build_report, NOT the conformance guard.
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr("substrate.assay.conformance._has_committed_record", lambda _root: True)
    try:
        arm_control = Arm(name="control", role="baseline", build=lambda _c: None)  # type: ignore[arg-type,return-value]
        arm_cand = Arm(name="candidate", role=FULL, build=lambda _c: None)  # type: ignore[arg-type,return-value]
        cases = tuple(Case(case_id=f"c{i}", payload={}, ground_truth=None) for i in range(4))
        suite = Suite(
            name="s",
            version="0.1",
            cases=cases,
            arms=(arm_control, arm_cand),
            oracle=type("O", (), {"grade": lambda self, _r, _g: None})(),
            control_arm="control",
            primary_metric="resolved",
            null_rule="",
        )
        # Control: 2 pass with REPRODUCED (agree_neg failure — should be reproduced_and_failed),
        # 2 fail with REPRODUCED (also reproduced_and_failed). Repro anti-correlated with pass.
        # Candidate: 4/4 pass with RESOLVED (agree_pos — resolved_and_passed).
        results = []
        for i in range(4):
            results.append(_cr(passed=(i < 2), repro="reproduced", arm="control", case_id=f"c{i}"))
            results.append(_cr(passed=True, repro="resolved", arm="candidate", case_id=f"c{i}"))
        report = build_report(suite, results)
        by_name = {a.arm: a for a in report.arms}

        # The candidate arm's delta path fires (control ran, arm != control, both complete) —
        # AND the repro fields are populated correctly.
        cand = by_name["candidate"]
        assert cand.delta_vs_control is not None  # paired comparison ran
        assert cand.repro_2x2 == {
            "resolved_and_passed": 4,
            "resolved_and_failed": 0,
            "reproduced_and_passed": 0,
            "reproduced_and_failed": 0,
        }
        # All-one-cell: chance agreement = 100%, kappa undefined per Cohen 1960.
        assert cand.repro_kappa is None
        assert cand.repro_agreement_rate == pytest.approx(1.0)

        # The control arm skips delta but STILL populates repro fields — it's an arm like any
        # other for the aggregation, just not the target of the paired comparison.
        ctrl = by_name["control"]
        assert ctrl.delta_vs_control is None  # control-vs-control not computed
        assert ctrl.repro_2x2 == {
            "resolved_and_passed": 0,
            "resolved_and_failed": 0,
            "reproduced_and_passed": 2,
            "reproduced_and_failed": 2,
        }
        # a=0, b=0, c=2, d=2, n=4. p_o = (a+d)/n = 0.5. Row marginals: row1=0, row2=4;
        # col marginals: col1=2, col2=2. p_e = (0*2 + 4*2)/16 = 0.5. κ = (0.5 - 0.5)/(1 - 0.5)
        # = 0.0 — no information beyond chance (repro constantly says REPRODUCED so it can't
        # predict pass vs fail). 1 - p_e = 0.5 ≠ 0, so κ is defined, not None.
        assert ctrl.repro_kappa == pytest.approx(0.0)
        assert ctrl.repro_agreement_rate == pytest.approx(0.5)
    finally:
        monkeypatch.undo()


def test_arm_report_resolve_per_call_efficiency_field():
    # Sprint 159: `resolve_per_call = passes / model_calls` is the secondary endpoint the
    # sprint 160 writeup uses to distinguish mechanism-driven gains from compute-driven ones
    # (Kapoor & Narayanan 2024). Verify: (a) computed correctly on measured runs, (b) `None`
    # when no calls were made (salvage/fail cell chain — 0/0 would ZeroDivisionError).
    arm = Arm(name="solver", role=FULL, build=lambda _c: None)  # type: ignore[arg-type,return-value]
    suite = Suite(
        name="s",
        version="0.1",
        cases=(Case(case_id="c0", payload={}, ground_truth=None),),
        arms=(arm,),
        oracle=type("O", (), {"grade": lambda self, _r, _g: None})(),
        control_arm="solver",
        primary_metric="resolved",
        null_rule="",
    )
    # Two trials of the same case, both passing (pass^k=1 collapses to one cell pass), 3 model
    # calls each -> passes=1 (one case, cell passed all trials) / calls=6 (summed across
    # trials) = 1/6. `passes` is the cell-collapsed count `build_report` uses, not the raw
    # per-trial pass count.
    metered = CaseResult(
        arm="solver",
        role=FULL,
        case_id="c0",
        trial=0,
        result=Result(
            passed=True, score=1.0, metric="r", oracle_class=EXTERNAL_GRADER, replayable=False
        ),
        usage=UsageTotals(
            prompt_tokens=100,
            completion_tokens=50,
            inference_ms=1000,
            model_calls=3,
            estimated=False,
        ),
        elapsed_ms=2000,
        root="",
    )
    metered2 = CaseResult(
        arm="solver",
        role=FULL,
        case_id="c0",
        trial=1,
        result=Result(
            passed=True, score=1.0, metric="r", oracle_class=EXTERNAL_GRADER, replayable=False
        ),
        usage=UsageTotals(
            prompt_tokens=100,
            completion_tokens=50,
            inference_ms=1000,
            model_calls=3,
            estimated=False,
        ),
        elapsed_ms=2000,
        root="",
    )
    report = build_report(suite, [metered, metered2])
    (line,) = report.arms
    assert line.resolve_per_call == pytest.approx(1 / 6)
    assert line.model_calls == 6

    # Zero-call arm (a salvage-only run producing no metered calls) -> resolve_per_call is None,
    # not a ZeroDivisionError.
    zero = _cr(True, "")  # UsageTotals(0,0,0,0,False) via _cr's stub
    report_zero = build_report(suite, [zero])
    (line_zero,) = report_zero.arms
    assert line_zero.model_calls == 0
    assert line_zero.resolve_per_call is None


def test_exact_mcnemar_is_still_here():
    # sanity: sprint 158 must not have accidentally displaced the McNemar helper the earlier
    # report tests rely on.
    assert exact_mcnemar_p(0, 0) == 1.0


# F2 fix (review 2026-08-08): per-arm recall aggregation on ArmReport.
def test_arm_report_mean_recall_and_full_recall_rate_aggregation():
    from substrate.assay.oracle import Result as _R

    arm = Arm(name="solver", role=FULL, build=lambda _c: None)  # type: ignore[arg-type,return-value]
    suite = Suite(
        name="s",
        version="0.1",
        cases=(
            Case(case_id="c0", payload={}, ground_truth=None),
            Case(case_id="c1", payload={}, ground_truth=None),
            Case(case_id="c2", payload={}, ground_truth=None),
        ),
        arms=(arm,),
        oracle=type("O", (), {"grade": lambda self, _r, _g: None})(),
        control_arm="solver",
        primary_metric="resolved",
        null_rule="",
    )

    # Three cells: recall 1.0/full=True, 0.5/full=False, None/None (no-signal cell).
    # Mean recall = (1.0 + 0.5) / 2 = 0.75 (None excluded from the mean).
    # Full recall rate = 1 of 2 = 0.5 (None excluded).
    def _cr_r(cid: str, recall: float | None, full: bool | None):
        return CaseResult(
            arm="solver",
            role=FULL,
            case_id=cid,
            trial=0,
            result=_R(
                passed=True,
                score=1.0,
                metric="r",
                oracle_class=EXTERNAL_GRADER,
                replayable=False,
                recall_at_k=recall,
                full_recall_at_k=full,
            ),
            usage=UsageTotals(0, 0, 0, 0, False),
            elapsed_ms=0,
            root="",
        )

    results = [
        _cr_r("c0", 1.0, True),
        _cr_r("c1", 0.5, False),
        _cr_r("c2", None, None),
    ]
    report = build_report(suite, results)
    (line,) = report.arms
    assert line.mean_recall_at_k == pytest.approx(0.75)
    assert line.full_recall_at_k_rate == pytest.approx(0.5)


def test_arm_report_recall_fields_none_when_no_cells_carry_recall():
    # A coding arm — no cell carries recall — leaves both fields None so a reader distinguishes
    # "no signal" from "signal was zero".
    arm = Arm(name="solver", role=FULL, build=lambda _c: None)  # type: ignore[arg-type,return-value]
    suite = Suite(
        name="s",
        version="0.1",
        cases=(Case(case_id="c0", payload={}, ground_truth=None),),
        arms=(arm,),
        oracle=type("O", (), {"grade": lambda self, _r, _g: None})(),
        control_arm="solver",
        primary_metric="resolved",
        null_rule="",
    )
    report = build_report(suite, [_cr(True, "")])  # coding-style: no recall on the Result
    (line,) = report.arms
    assert line.mean_recall_at_k is None
    assert line.full_recall_at_k_rate is None
