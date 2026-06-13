"""Conformance-harness tests (product §7; the v1.0 release-gate spine).

Asserts the harness itself: the per-check three-state status (PASS/FAIL/DEFERRED), that
check 6 is a GENUINE third state (not a green pass), and the report semantics. Runs with the
perf probe OFF (check 15 has its own dedicated benchmark + an honest open-floor status), so
this stays green and fast while never hiding the deferred/perf truth."""

import pytest

from substrate.conformance import Status, run_conformance


@pytest.mark.timeout(60)
async def test_all_checks_run_and_none_fail_except_perf():
    # perf off: check 15 becomes DEFERRED (covered by the dedicated benchmark + surfaced
    # floor finding), so the suite has zero FAILs and the deferred set is {6, 15}.
    report = await run_conformance(include_perf=False)
    assert len(report.results) == 17
    assert report.failed == 0, [r for r in report.results if r.status is Status.FAIL]
    # every check is PASS or DEFERRED
    assert all(r.status in (Status.PASS, Status.DEFERRED) for r in report.results)


@pytest.mark.timeout(60)
async def test_check_6_is_deferred_not_pass():
    # CRITICAL (carry-forward b): check 6 (Level-3b byte-identity) MUST be a genuine third
    # state — neither PASS nor FAIL — so it can never read as green (the silent-pass the A1
    # amendment exists to prevent).
    report = await run_conformance(include_perf=False)
    c6 = next(r for r in report.results if r.number == 6)
    assert c6.status is Status.DEFERRED
    assert c6.status is not Status.PASS
    assert "3b" in c6.detail.lower() or "deferred" in c6.detail.lower()


@pytest.mark.timeout(60)
async def test_all_non_failing_is_true_when_only_deferrals_remain():
    report = await run_conformance(include_perf=False)
    # no FAIL -> the gate is "non-failing"; but deferred checks are reported distinctly and do
    # not silently count as passes.
    assert report.all_non_failing is True
    assert report.deferred >= 1  # at least check 6
    assert report.passed + report.failed + report.deferred == 17


@pytest.mark.timeout(120)
async def test_perf_check_reports_a_real_measured_rate():
    # with perf ON, check 15 runs the floor probe and reports the REAL rate. On hardware below
    # the floor it FAILs honestly with the measured number (not fudged); above it, PASS. Either
    # way the detail carries a real "appends/sec" measurement — never a fabricated green.
    report = await run_conformance(include_perf=True)
    c15 = next(r for r in report.results if r.number == 15)
    assert c15.status in (Status.PASS, Status.FAIL)  # a real verdict, never DEFERRED-as-skip
    assert "appends/sec" in c15.detail
