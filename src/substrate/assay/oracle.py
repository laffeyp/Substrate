"""The Oracle taxonomy — Sprint 2 of the objective-validation ("assay") layer.

An Oracle grades ONE inner run (an Arm's run on a Case) against that Case's ground truth and returns
a typed Result. The round-1 design (docs/benchmarking-design-round1.md §3) splits Oracles into two
classes, and the split is load-bearing for honesty:

  - LogProjectionOracle — grades by reading a typed terminal-state value off the inner RECORD and
    comparing it to ground truth. No external system runs; the record IS the evidence, so the grade
    re-derives identically on replay. replayable=True.
  - ExternalGraderOracle — grades by running an EXTERNAL system (a test harness, a Docker image, a
    benchmark DB) against the run's output, then recording its verdict. The truth source is an
    external, non-deterministic process (exactly coding_flow's gate), so the grade is a real
    measurement captured ONCE: replay reproduces the orchestration, not this verdict. replayable=False.

The `replayable` flag rides on every Result so a reader can never mistake a run-and-observe grade for
a reproducible one — the honesty the design demands, enforced in the data rather than a comment.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from typing import Any, Protocol, runtime_checkable

from msgspec import Struct

# A record is what `substrate.api.read_record` yields: an ordered sequence of envelope dicts, each
# with at least "kind" and "payload". The Oracle reads it; it does not depend on how it was produced.
Envelope = Mapping[str, Any]
Record = Iterable[Envelope]

LOG_PROJECTION = "log-projection"
EXTERNAL_GRADER = "external-grader"


class Result(Struct, frozen=True):
    """The grade for one inner run against one Case's ground truth.

    `passed` is the boolean outcome; `score` is the primary numeric the Report aggregates (1.0/0.0
    for a pass/fail oracle, or a metric value in [0, 1]); `metric` names what `score` measures
    ("resolved", "exact_match", ...). `oracle_class` and `replayable` record HOW the grade was
    reached, so a downstream Report can label run-and-observe grades honestly. `detail` is a short
    human-readable note (observed vs target, or the external grader's summary).

    `grader_error_band` (sprint 153, ratified 2026-08-08) is the known residual oracle error for
    this benchmark — the fraction of `passed=True` verdicts that are actually incorrect per external
    validation. Xia & Chen (2025, "Are 'Solved Issues' in SWE-bench Really Solved Correctly?",
    arxiv 2503.15223) put ~0.078 on SWE-bench Lite; SWE-Bench+ (Aleithan et al. 2024,
    arxiv 2410.06992) reports a considerably larger contamination rate (~0.30) on a different
    axis — cite whichever residual matches the specific claim. SWE-bench Verified is ~0.02;
    SWE-bench-Live is `None` (not published). The value rides on the Result so a headline that
    reports 108 resolved can honestly print `108 ± 0.078 * 108 ≈ 108 ± 8` — a bare `108` reads as
    ground truth when it isn't. `None` = no residual known/asserted for this oracle; the reader
    should not compute an error band. Additive with default `None`; existing callers unchanged."""

    passed: bool
    score: float
    metric: str
    oracle_class: str
    replayable: bool
    detail: str = ""
    grader_error_band: float | None = None


@runtime_checkable
class Oracle(Protocol):
    """Grade one inner run's record against a Case's ground truth -> Result."""

    def grade(self, record: Record, ground_truth: Any) -> Result: ...


class LogProjectionOracle:
    """Deterministic, replayable (design §3, log-projection class).

    Grade by projecting a value off the inner record — a typed terminal-state event the topology put
    on the log — and comparing it to ground truth. `extract` pulls the observed value from the record
    (e.g. the FinalAnswer text, a final-state event); `compare` decides pass (default: equality). No
    external system, so the grade is a pure function of the record and re-derives on replay."""

    def __init__(
        self,
        *,
        extract: Callable[[list[Envelope]], Any],
        metric: str = "match",
        compare: Callable[[Any, Any], bool] | None = None,
    ) -> None:
        self._extract = extract
        self._metric = metric
        self._compare: Callable[[Any, Any], bool] = compare or (
            lambda observed, target: bool(observed == target)
        )

    def grade(self, record: Record, ground_truth: Any) -> Result:
        envelopes = list(record)
        observed = self._extract(envelopes)
        passed = self._compare(observed, ground_truth)
        return Result(
            passed=passed,
            score=1.0 if passed else 0.0,
            metric=self._metric,
            oracle_class=LOG_PROJECTION,
            replayable=True,
            detail=f"observed={observed!r} target={ground_truth!r}",
        )


class ExternalGraderOracle:
    """Run-and-observe, NOT replayable (design §3, external-grader class).

    Grade by running an EXTERNAL system against the run's output and reading its verdict. `grader`
    receives the inner record and the Case ground truth, runs the external process (a test harness, a
    Docker image, a benchmark DB), and returns (passed, detail). The truth source is external and
    non-deterministic, so the grade is captured once; the Result is stamped replayable=False so it is
    never mistaken for a reproducible log-projection grade."""

    def __init__(
        self,
        *,
        grader: Callable[[list[Envelope], Any], tuple[bool, str]],
        metric: str,
    ) -> None:
        self._grader = grader
        self._metric = metric

    def grade(self, record: Record, ground_truth: Any) -> Result:
        envelopes = list(record)
        passed, detail = self._grader(envelopes, ground_truth)
        return Result(
            passed=passed,
            score=1.0 if passed else 0.0,
            metric=self._metric,
            oracle_class=EXTERNAL_GRADER,
            replayable=False,
            detail=detail,
        )
