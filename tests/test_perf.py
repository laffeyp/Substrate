"""N-PERF-1 performance floor (product N-PERF-1 as amended by A2.1; technical §18;
conformance check 15).

Measures sustained append throughput at the F-PRED-1 filtered reference shape (50 Triggers
across 10 kinds / 10 Views, subscription-filtered to <=5 substantive per append) and records
the REAL number, gating on the floor.

FLOOR = 40,000 appends/sec (product amendment A2.1). The original DRAFT 7 floor of 100K was
derived from a D-9 prototype that did NOT measure the per-frame RFC 8785 canonical encoding
the product requires for D-7 byte-identity — it measured a lighter operation than a real
append. The shipping implementation sustains ~56K/sec at this shape on an idle machine; the
dominant per-append cost is the pure-Python rfc8785 encoder (correctness-critical, left
as-is). (A compiled JCS encoder is the post-1.0 lever if a deterministic firehose ever needs
more; do not hand-write one — byte-identity is the contract.)

WHY THE FLOOR GATE IS OPT-IN (review #9): append throughput is hardware- and
contention-sensitive — the same code measured ~56K on an idle box and ~20K on a loaded one.
A hard `assert rate >= FLOOR` in the default unit suite therefore couples suite green-ness to
machine load, which has nothing to do with code correctness, and flakes on any busy CI runner
or dev box. So the floor gate is SKIPPED by default and opt-in via `SUBSTRATE_PERF_GATE=1`
(run it deliberately on a controlled machine). The honest release-time floor lives in
`substrate conformance` check 15, which measures and FAILs honestly on the host it runs on.
The always-on `test_perf_probe_runs_and_reports_a_real_number` below proves the probe works
without gating on throughput, so the suite is deterministically green everywhere."""

import os

import pytest

from substrate.conformance_perf import measure_append_rate

_FLOOR = 40_000  # N-PERF-1 appends/sec, per product amendment A2.1 (was 100K)


@pytest.mark.skipif(
    not os.environ.get("SUBSTRATE_PERF_GATE"),
    reason="throughput is hardware/contention-sensitive; the floor is gated at release via "
    "`substrate conformance` check 15. Opt in deliberately on a controlled box with "
    "SUBSTRATE_PERF_GATE=1.",
)
@pytest.mark.timeout(60)
async def test_n_perf_1_floor_reference_shape(tmp_path):
    rate, n = await measure_append_rate(tmp_path / "perf", burst=20_000)
    print(f"\nN-PERF-1 reference shape: {rate:,.0f} appends/sec (n={n}, floor {_FLOOR:,})")
    assert rate >= _FLOOR, f"{rate:,.0f} appends/sec < floor {_FLOOR:,} (measured, not fudged)"


@pytest.mark.timeout(60)
async def test_perf_probe_runs_and_reports_a_real_number(tmp_path):
    # this one is NOT a floor gate — it just proves the probe works and the number is sane
    # (positive, plausible), so the harness's check 15 has a trustworthy measurement.
    rate, n = await measure_append_rate(tmp_path / "perf", burst=5_000)
    assert n >= 5_000  # all appends landed
    assert rate > 0  # a real positive throughput was measured
