"""The control plane — run each Arm on each Case, grade, collect (Sprint 4 execution).

Each Arm is a normal top-level run at its OWN minted root — not a meta-topology — and the Oracle reads
the resulting record. `embedded_substrate` is for a topology that embeds a sub-substrate; the harness
does not need it. NB: the design doc contradicts itself here — §A1 sketches arms-via-embedded_substrate
with two records, §A5 argues no outer topology. This implementation takes the plain-Runtime path as the
simpler one; the choice is deferred to open-decision §8.3. Do not cite the design as cleanly mandating
either form.

Two TIME axes, kept distinct because conflating them inverts the concurrency benefit: the REAL
elapsed wall-clock of each run (timed around `Runtime.run` — this is where N concurrent Producers show
up as a DROP), and the SUM of per-call inference latencies (a work measure that OVERCOUNTS when calls
overlap, so it must never be read as latency). Tokens and both times are measurements, not a cost
(there is no money here).
"""

from __future__ import annotations

import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from msgspec import Struct

from .. import api
from .oracle import Oracle, Result
from .suite import Arm, Case, Suite


class UsageTotals(Struct, frozen=True):
    """Per-run token totals + total INFERENCE time, summed from the ModelUsage events on the record.

    `inference_ms` is the SUM of per-call inference latencies — a work/throughput measure, NOT elapsed
    wall-clock: when N model calls run concurrently their per-call latencies OVERLAP, so the sum
    overcounts the real elapsed time and must never be read as latency. The real wall-clock of the
    whole run is `CaseResult.elapsed_ms` (timed around the run), which is where concurrency shows up.
    `estimated` is True if ANY usage on the record was a word-count stand-in rather than provider truth."""

    prompt_tokens: int
    completion_tokens: int
    inference_ms: int  # SUM of per-call inference latencies (work) — NOT elapsed wall-clock
    model_calls: int
    estimated: bool


def _sum_usage(record: Sequence[Mapping[str, Any]]) -> UsageTotals:
    usages = [e["payload"] for e in record if e["kind"] == "ModelUsage"]
    return UsageTotals(
        prompt_tokens=sum(int(u["prompt_tokens"]) for u in usages),
        completion_tokens=sum(int(u["completion_tokens"]) for u in usages),
        inference_ms=sum(
            int(u["wall_ms"]) for u in usages
        ),  # per-call wall_ms summed = work, not latency
        model_calls=len(usages),
        estimated=any(bool(u.get("estimated", False)) for u in usages),
    )


@dataclass(frozen=True)
class CaseResult:
    """The graded outcome of one Arm running one Case on one Trial, plus the run's token/inference
    totals, the REAL elapsed wall-clock of the run (`elapsed_ms` — the latency axis, where concurrency
    shows up), and the root its record sits at (so a reader can open the inner record behind any number)."""

    arm: str
    role: str
    case_id: str
    trial: int
    result: Result
    usage: UsageTotals
    elapsed_ms: int
    root: str


async def run_arm_on_case(
    arm: Arm, case: Case, oracle: Oracle, root: Path | str, *, trial: int = 0
) -> CaseResult:
    """Run one Arm on one Case at `root`: build the topology, run it as a top-level run, grade the
    record with the Oracle. `elapsed_ms` times the actual run (the wall-clock/latency axis); the usage
    totals carry tokens + summed inference time (work). The record stays on disk at `root` as evidence."""
    topology = arm.build(case)
    started = time.monotonic()
    await api.Runtime(root).run(topology)
    elapsed_ms = int((time.monotonic() - started) * 1000)
    record: list[Mapping[str, Any]] = list(api.read_record(root))
    result = oracle.grade(record, case.ground_truth)
    return CaseResult(
        arm=arm.name,
        role=arm.role,
        case_id=case.case_id,
        trial=trial,
        result=result,
        usage=_sum_usage(record),
        elapsed_ms=elapsed_ms,
        root=str(root),
    )


async def run_suite(suite: Suite, root_dir: Path | str, *, trials: int = 1) -> list[CaseResult]:
    """Run every (Arm, Case, Trial) at a unique minted root and return all CaseResults. Trials repeat
    a (non-deterministic, real-model) Arm to build a distribution; for a deterministic Arm the trials
    are identical, so the per-Arm variance is honestly zero."""
    base = Path(root_dir)
    results: list[CaseResult] = []
    for arm in suite.arms:
        for case in suite.cases:
            for t in range(trials):
                root = base / f"{arm.name}__{case.case_id}__t{t}"
                results.append(await run_arm_on_case(arm, case, suite.oracle, root, trial=t))
    return results
