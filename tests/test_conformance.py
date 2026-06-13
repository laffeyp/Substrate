"""Conformance-harness tests (product §7; the v1.0 release-gate spine).

Asserts the harness itself: the per-check three-state status (PASS/FAIL/DEFERRED), that
check 6 is a GENUINE third state (not a green pass), and the report semantics. Runs with the
perf probe OFF (check 15 has its own dedicated benchmark + an honest open-floor status), so
this stays green and fast while never hiding the deferred/perf truth."""

import pytest

from substrate.conformance import Status, run_conformance


@pytest.mark.timeout(60)
async def test_all_checks_run_and_none_fail_except_perf():
    # perf off: check 15 becomes SKIPPED (not DEFERRED — review #5 FIX B), check 6 DEFERRED,
    # so the suite has zero FAILs.
    report = await run_conformance(include_perf=False)
    assert len(report.results) == 17
    assert report.failed == 0, [r for r in report.results if r.status is Status.FAIL]
    # every check is PASS, DEFERRED (check 6), or SKIPPED (check 15 under --no-perf)
    assert all(r.status in (Status.PASS, Status.DEFERRED, Status.SKIPPED) for r in report.results)


@pytest.mark.timeout(60)
async def test_check_6_is_deferred_not_pass():
    # CRITICAL (carry-forward b): check 6 (Level-3b byte-identity) MUST be a genuine third
    # state — neither PASS nor FAIL — so it can never read as green (the silent-pass the A1
    # amendment exists to prevent).
    report = await run_conformance(include_perf=False)
    c6 = next(r for r in report.results if r.number == 6)
    assert c6.status is Status.DEFERRED
    assert c6.status is not Status.PASS
    # FIX A: the deferral is SCOPED to 3(b) — the detail must say Level 2 PASSED (not masked).
    assert "Level 2 PASSED" in c6.detail
    assert "3(b)" in c6.detail or "3b" in c6.detail.lower()


@pytest.mark.timeout(60)
async def test_check_6_fails_on_a_level2_mismatch_not_masked_as_deferred():
    # FIX A (honesty): Level 2 SHIPS — a genuine Level-2 input-hash mismatch inside check 6
    # must FAIL, NOT be masked as DEFERRED. Drive it by patching replay to report a mismatch.
    import substrate.conformance as conf
    from substrate.replay import HashMismatch, ReplayResult

    real_replay = conf.replay

    def fake_replay(record, level="1"):
        if level == "2":
            return ReplayResult(
                level="2",
                frame_count=1,
                counts={},
                complete=True,
                decisions_verified=1,
                mismatches=(
                    HashMismatch(seq=3, trigger_id="t", recorded="sha256:a", recomputed="sha256:b"),
                ),
            )
        return real_replay(record, level=level)

    conf.replay = fake_replay
    try:
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as d:
            result = await conf._check_6_replay_roundtrip(Path(d) / "r")
        assert result.status is Status.FAIL  # not DEFERRED — Level 2 must not be masked
        assert "Level 2" in result.detail
    finally:
        conf.replay = real_replay


@pytest.mark.timeout(60)
async def test_check_15_skip_is_skipped_not_deferred():
    # FIX B: --no-perf yields SKIPPED (run-time skip), NOT DEFERRED (spec-amended) — the two
    # must be distinguishable so a skip never reads as the ruled deferral.
    report = await run_conformance(include_perf=False)
    c15 = next(r for r in report.results if r.number == 15)
    assert c15.status is Status.SKIPPED
    assert c15.status is not Status.DEFERRED


@pytest.mark.timeout(60)
async def test_all_non_failing_is_true_when_only_deferrals_remain():
    report = await run_conformance(include_perf=False)
    # no FAIL -> the gate is "non-failing"; but deferred checks are reported distinctly and do
    # not silently count as passes.
    assert report.all_non_failing is True
    assert report.deferred >= 1  # at least check 6 (spec-amended)
    assert report.skipped == 1  # check 15 under --no-perf
    # the four states partition all 17 checks — nothing folded silently into "passed"
    assert report.passed + report.failed + report.deferred + report.skipped == 17


@pytest.mark.timeout(120)
async def test_perf_check_reports_a_real_measured_rate():
    # with perf ON, check 15 runs the floor probe and reports the REAL rate. On hardware below
    # the floor it FAILs honestly with the measured number (not fudged); above it, PASS. Either
    # way the detail carries a real "appends/sec" measurement — never a fabricated green.
    report = await run_conformance(include_perf=True)
    c15 = next(r for r in report.results if r.number == 15)
    assert c15.status in (Status.PASS, Status.FAIL)  # a real verdict, never DEFERRED-as-skip
    assert "appends/sec" in c15.detail
