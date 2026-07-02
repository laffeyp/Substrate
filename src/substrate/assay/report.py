"""Report + paired statistics — Sprint 4 output.

Per-Arm pass-rate over the Suite; each non-control Arm compared to the control by an EXACT McNemar
test PAIRED across Cases (design §4.6 — pairing removes between-Case variance; the exact binomial
handles the small discordant counts a real run produces). Measurements are reported SEPARATELY:
quality (pass rate), completion tokens, elapsed wall-clock (`elapsed_ms` — the latency axis, where N
concurrent Producers show up as a DROP), and summed inference time (`inference_ms` — a work measure
that overcounts under concurrency, never read as latency). Never fused; none is a cost. The
delta-vs-control is GATED by the control-ran conformance check (Sprint 3): no control on the log, no
delta — the value stays None and the check state says why.

The PRIMARY significance surface is a PAIRED two-level bootstrap on Δ-pass^k (`stats`): resample Cases,
then trials within each Case, so trial-level uncertainty is CARRIED, not collapsed. A TOST equivalence
verdict against the Suite's PRE-REGISTERED margin distinguishes superior / equivalent (CI inside
±margin — a REAL null) / inferior / inconclusive — non-significance is never silently read as "no
effect" (the crack the external review caught). Multiplicity across the arm matrix is controlled by
Benjamini-Hochberg FDR. The exact McNemar p-value is kept as a SECONDARY binary cross-check. The
bootstrap is seeded, so the Report is REPEATABLE (same results -> same CI).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from .conformance import PASS, ControlRanCheck, check_control_ran
from .run import CaseResult
from .stats import DeltaCI, benjamini_hochberg, bootstrap_delta_pass_k
from .suite import Suite


def exact_mcnemar_p(b: int, c: int) -> float:
    """Two-sided exact McNemar p-value over discordant pairs (binomial on min(b, c), p=0.5). b =
    control passed & arm failed; c = control failed & arm passed. n = b + c = 0 -> 1.0 (no evidence)."""
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    tail = sum(math.comb(n, i) for i in range(k + 1)) * (0.5**n)
    return min(1.0, 2.0 * tail)


@dataclass(frozen=True)
class ArmReport:
    """One Arm's line in the Report. `delta_vs_control` / `discordant_*` / `p_value` are None for the
    control Arm itself AND whenever the control did not run (gated by the conformance check). `p_value`
    is RAW (uncorrected — see module docstring). `elapsed_ms` is the real wall-clock (latency, where
    concurrency shows up); `inference_ms` is summed per-call latency (work, overcounts under
    concurrency). Token/time totals are separate fields; `estimated_usage` flags them as estimates."""

    arm: str
    role: str
    n_cases: int
    passes: int
    pass_rate: (
        float  # pass^k-COLLAPSED reliable-solve rate (a cell counts only if ALL trials passed)
    )
    pass_at_1: float  # per-trial (pass@1) success rate — the OTHER currency; the gap to pass_rate is flakiness
    complete: (
        bool  # graded EVERY suite Case — a verdict is gated on this (no claim off a partial run)
    )
    delta_vs_control: (
        float | None
    )  # pass^k-collapsed Δ (same currency as `passes`) — the harsher, honest one
    discordant_control_only: int | None  # b: control passed, arm failed
    discordant_arm_only: int | None  # c: control failed, arm passed
    p_value: float | None  # exact McNemar (binary) — SECONDARY cross-check
    # PRIMARY surface: paired two-level bootstrap on Δ-pass^k + TOST verdict + BH-FDR. None for the
    # control Arm itself and whenever the control did not run.
    delta_pass_k: float | None  # arm pass^k minus control pass^k (bootstrap point estimate)
    ci_low: float | None
    ci_high: float | None
    bootstrap_p: float | None  # RAW two-sided; `fdr_significant` applies BH across the arm matrix
    equivalence: str | None  # superior | equivalent | inferior | inconclusive (vs the margin)
    fdr_significant: bool | None  # BH-FDR reject across the non-control arms
    completion_tokens: int
    elapsed_ms: int  # real wall-clock summed over the arm's runs — the latency axis
    inference_ms: int  # summed per-call inference time — work, NOT latency
    model_calls: int
    estimated_usage: bool


@dataclass(frozen=True)
class Report:
    """The whole comparison. `control_check` is the three-state guard; if it is not `pass`, every
    Arm's delta is None — there is no delta number without a control that ran."""

    suite: str
    version: str
    primary_metric: str
    control_arm: str
    null_rule: str
    control_check: ControlRanCheck
    arms: tuple[ArmReport, ...]


def _cell_passed(results: Sequence[CaseResult]) -> bool | None:
    """pass^k reliability for one (Arm, Case) cell: passes iff every trial passed. None if the cell
    has no results (the Arm did not run this Case)."""
    if not results:
        return None
    return all(r.result.passed for r in results)


@dataclass(frozen=True)
class _Mid:
    """Per-Arm intermediate, computed before BH-FDR (which needs every non-control arm's p at once)."""

    arm: str
    role: str
    n_cases: int
    passes: int
    pass_rate: float
    pass_at_1: float
    complete: bool
    delta_vs_control: float | None
    b: int | None
    c: int | None
    mcnemar_p: float | None
    dci: DeltaCI | None
    completion: int
    elapsed: int
    inference: int
    calls: int
    estimated: bool


def _arm_trial_bools(
    results: Sequence[CaseResult], arm_name: str, case_ids: Sequence[str]
) -> dict[str, list[bool]]:
    """case_id -> per-trial pass booleans for (arm, case), trial-ordered. Cases the Arm never ran are
    omitted, so the bootstrap pairs only Cases both arms graded."""
    out: dict[str, list[bool]] = {}
    for cid in case_ids:
        cell = sorted(
            (r for r in results if r.arm == arm_name and r.case_id == cid), key=lambda r: r.trial
        )
        if cell:
            out[cid] = [r.result.passed for r in cell]
    return out


def build_report(suite: Suite, results: Sequence[CaseResult]) -> Report:
    check = check_control_ran(results, suite)
    case_ids = [c.case_id for c in suite.cases]

    def cell_map(arm_name: str) -> dict[str, bool | None]:
        return {
            cid: _cell_passed([r for r in results if r.arm == arm_name and r.case_id == cid])
            for cid in case_ids
        }

    control_map = cell_map(suite.control_arm) if check.state == PASS else {}
    control_bools = (
        _arm_trial_bools(results, suite.control_arm, case_ids) if check.state == PASS else {}
    )
    # ARM-COMPLETENESS gate (review): a verdict needs every Case graded in BOTH the arm AND the control
    # — a half-finished run (the live sweep) must not yield a confirmatory delta/CI/verdict.
    control_complete = check.state == PASS and all(
        control_map.get(cid) is not None for cid in case_ids
    )

    mids: list[_Mid] = []
    for arm in suite.arms:
        cells = cell_map(arm.name)
        graded = [cid for cid in case_ids if cells[cid] is not None]
        passes = sum(1 for cid in graded if cells[cid])
        n = len(graded)
        arm_complete = n == len(case_ids)  # this arm graded every Case in the suite
        arm_results = [r for r in results if r.arm == arm.name]

        delta_vs_control: float | None = None
        b_val: int | None = None
        c_val: int | None = None
        p_val: float | None = None
        dci: DeltaCI | None = None
        # GATE: a delta/verdict exists only if the control ran on every Case (check PASS), this is not
        # the control, AND both this arm and the control graded every Case (completeness — no verdict
        # off a partial run).
        if (
            check.state == PASS
            and arm.name != suite.control_arm
            and arm_complete
            and control_complete
        ):
            # McNemar on the pass^k-collapsed cells — PAIRED over the Cases both arms graded.
            b = c = control_passes = arm_passes = paired = 0
            for cid in case_ids:
                cm = control_map.get(cid)
                am = cells.get(cid)
                if cm is None or am is None:
                    continue
                paired += 1
                control_passes += 1 if cm else 0
                arm_passes += 1 if am else 0
                if cm and not am:
                    b += 1
                elif (not cm) and am:
                    c += 1
            if paired:
                delta_vs_control = (arm_passes - control_passes) / paired
                b_val, c_val, p_val = b, c, exact_mcnemar_p(b, c)
            # PRIMARY: paired two-level bootstrap on Δ-pass^k + TOST verdict (carries trial variance).
            dci = bootstrap_delta_pass_k(
                _arm_trial_bools(results, arm.name, case_ids),
                control_bools,
                k=suite.pass_k,
                margin=suite.equivalence_margin,
                seed=0,
            )

        mids.append(
            _Mid(
                arm=arm.name,
                role=arm.role,
                n_cases=n,
                passes=passes,
                pass_rate=passes / n if n else 0.0,
                pass_at_1=(sum(1 for r in arm_results if r.result.passed) / len(arm_results))
                if arm_results
                else 0.0,
                complete=arm_complete,
                delta_vs_control=delta_vs_control,
                b=b_val,
                c=c_val,
                mcnemar_p=p_val,
                dci=dci,
                completion=sum(r.usage.completion_tokens for r in arm_results),
                elapsed=sum(r.elapsed_ms for r in arm_results),
                inference=sum(r.usage.inference_ms for r in arm_results),
                calls=sum(r.usage.model_calls for r in arm_results),
                estimated=any(r.usage.estimated for r in arm_results),
            )
        )

    # BH-FDR across the non-control arms' bootstrap p-values (the multiplicity correction).
    nonctrl = [(i, m.dci) for i, m in enumerate(mids) if m.dci is not None]
    rejects = benjamini_hochberg([dci.p_two_sided for _, dci in nonctrl], alpha=0.05)
    fdr = {nonctrl[j][0]: rejects[j] for j in range(len(nonctrl))}

    arm_reports = tuple(
        ArmReport(
            arm=m.arm,
            role=m.role,
            n_cases=m.n_cases,
            passes=m.passes,
            pass_rate=m.pass_rate,
            pass_at_1=m.pass_at_1,
            complete=m.complete,
            delta_vs_control=m.delta_vs_control,
            discordant_control_only=m.b,
            discordant_arm_only=m.c,
            p_value=m.mcnemar_p,
            delta_pass_k=(m.dci.delta if m.dci else None),
            ci_low=(m.dci.ci_low if m.dci else None),
            ci_high=(m.dci.ci_high if m.dci else None),
            bootstrap_p=(m.dci.p_two_sided if m.dci else None),
            equivalence=(m.dci.verdict if m.dci else None),
            fdr_significant=(fdr.get(i) if m.dci else None),
            completion_tokens=m.completion,
            elapsed_ms=m.elapsed,
            inference_ms=m.inference,
            model_calls=m.calls,
            estimated_usage=m.estimated,
        )
        for i, m in enumerate(mids)
    )

    return Report(
        suite=suite.name,
        version=suite.version,
        primary_metric=suite.primary_metric,
        control_arm=suite.control_arm,
        null_rule=suite.null_rule,
        control_check=check,
        arms=arm_reports,
    )
