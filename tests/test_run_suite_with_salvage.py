"""Sprint 199 (roadmap v2 S7a): the generic per-cell orchestrator `run_suite_with_salvage`.

The confirmatory SWE-bench runner has grown to 1045 lines because every generic piece — cell
concurrency, salvage short-circuit, per-cell wall-clock, typed exception classification,
row-write serialization — was written inline. Sprint 199 lifts that into `assay/run.py` so
Sprint 199b (roadmap v2 S7b) can rewrite the runner around it in ~350 lines.

Tests pin the extracted contract:
- Every triple runs; outcomes carry (arm, case, trial, source, root, ...).
- A cell whose record already sits under `salvage_dir` regrades WITHOUT calling the topology
  (source="salvage", usage=_ZERO, elapsed=0).
- A cell that raises past the classifier's halt gate stops the sweep with the original traceback.
- A cell that raises with halt=False becomes an ERROR outcome and the sweep continues.
- Per-cell `PerCellBudget.time_s` trips `asyncio.wait_for` — the timeout raises TimeoutError
  the classifier maps to (`timed_out`, halt=False), so the sweep continues past the flake.
- `on_outcome` fires exactly once per completed cell (RUN + SALVAGE + ERROR).
- `skip(arm, case, trial)` bypasses a triple entirely; skipped triples are not in the returned list.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from msgspec import Struct

from substrate import api
from substrate.assay.oracle import LogProjectionOracle, Verdict
from substrate.assay.run import (
    CellOutcome,
    CellSource,
    PerCellBudget,
    run_suite_with_salvage,
)
from substrate.assay.suite import Arm, Case, Suite


class _Answer(Struct, frozen=True):
    text: str


async def _echo_producer_factory():
    """A producer that emits one Answer(text=payload['text']). The payload lands via the
    initial() input the Arm's build sets."""

    async def _echo(inp):
        yield _Answer(text=str(inp["text"]))

    return _echo


def _make_arm(name: str, role: str = "full") -> Arm:
    def _build(case: Case) -> api.Topology:
        text = str(case.payload["text"])

        def topo(b):
            b.producer_kind(
                "echo",
                schemas=[_Answer],
                schema_version=1,
                factory=lambda: _echo_from(text),
            )
            b.initial("echo", input={"text": text})
            b.termination(api.threshold_count("substrate.ProducerCompleted", 1))

        return topo

    return Arm(name=name, role=role, build=_build)


def _echo_from(text: str):
    async def _echo(inp):
        yield _Answer(text=str(inp["text"]) if isinstance(inp, dict) else text)

    return _echo


def _text_oracle() -> LogProjectionOracle:
    def _extract(envelopes):
        for e in envelopes:
            if e["kind"] == "_Answer":
                return e["payload"]["text"]
        return None

    return LogProjectionOracle(extract=_extract, metric="text_match")


def _suite(cases_texts: list[tuple[str, str]], arm_names: list[str]) -> Suite:
    cases = tuple(Case(case_id=cid, payload={"text": t}, ground_truth=t) for cid, t in cases_texts)
    arms = tuple(_make_arm(n) for n in arm_names)
    return Suite(
        name="echo_suite",
        version="v1",
        cases=cases,
        arms=arms,
        oracle=_text_oracle(),
        control_arm=arm_names[0],
        primary_metric="text_match",
        null_rule="no-null-rule",
    )


async def test_every_triple_runs_and_grades(tmp_path: Path):
    """Baseline: two arms × two cases × one trial = four outcomes, all source='run',
    all pass on the echo oracle."""
    suite = _suite([("c1", "alpha"), ("c2", "beta")], ["a1", "a2"])
    outcomes = await run_suite_with_salvage(suite, tmp_path, trials=1)
    assert len(outcomes) == 4
    for o in outcomes:
        assert o.source is CellSource.RUN
        assert o.result is not None
        assert o.result.verdict is Verdict.PASS


async def test_salvage_short_circuits_the_topology(tmp_path: Path):
    """A pre-existing record under `salvage_dir` regrades via the oracle without calling
    the topology. The outcome carries source='salvage' + usage=_ZERO + elapsed=0. Prove
    the topology never runs by making the salvage record's Answer disagree with the case
    ground_truth — the salvage grade FAILS while a fresh run would have PASSED."""
    # Case ground truth is "true" but the salvage record says "false" — a fresh run would
    # pass; salvage returns fail.
    suite = _suite([("c1", "true")], ["a1"])
    salvage_dir = tmp_path / "salv"
    salv_cell = salvage_dir / "a1__c1__t0"
    salv_cell.mkdir(parents=True)
    # Minimal record: one Answer event with text="false" so the oracle grades fail.
    await api.Runtime(salv_cell).run(
        lambda b: (
            b.producer_kind(
                "echo", schemas=[_Answer], schema_version=1, factory=_echo_producer_factory_wrong
            ),
            b.initial("echo", input=None),
            b.termination(api.threshold_count("substrate.ProducerCompleted", 1)),
        )
    )
    outcomes = await run_suite_with_salvage(
        suite, tmp_path / "run", trials=1, salvage_dir=salvage_dir
    )
    assert len(outcomes) == 1
    o = outcomes[0]
    assert o.source is CellSource.SALVAGE
    assert o.result is not None
    assert o.result.verdict is Verdict.FAIL, (
        "salvage regrade must reflect the record, not a fresh run"
    )
    assert o.elapsed_ms == 0
    assert o.usage is not None
    assert o.usage.model_calls == 0


def _echo_producer_factory_wrong():
    async def _echo(_inp):
        yield _Answer(text="false")

    return _echo


async def test_classified_halt_re_raises_original_exception(tmp_path: Path):
    """A cell that raises past a classifier's halt gate stops the sweep with the ORIGINAL
    exception — not a synthetic wrapper. The runner-side classifier owns the taxonomy;
    the loop owns the control flow."""

    class _Boom(RuntimeError):
        pass

    def _arm_that_raises(name: str) -> Arm:
        def _build(case: Case) -> api.Topology:
            def topo(b):
                async def _raiser(_inp):
                    raise _Boom("data-bug")
                    yield  # unreachable

                b.producer_kind(
                    "raiser", schemas=[_Answer], schema_version=1, factory=lambda: _raiser
                )
                b.initial("raiser", input=None)
                b.termination(api.threshold_count("substrate.ProducerStarted", 1))

            return topo

        return Arm(name=name, role="full", build=_build)

    cases = (Case(case_id="c1", payload={"text": "x"}, ground_truth="x"),)
    arms = (_arm_that_raises("halt_arm"),)

    # A Producer raise becomes ProducerFailed inside Runtime, so `run_arm_on_case` returns
    # a graded Result rather than raising. To exercise the cell-loop's halt path we make the
    # ORACLE raise: it runs on the record after the run completes, and its exception
    # propagates through `asyncio.to_thread(oracle.grade, ...)` into the cell try/except.
    class _RaisingOracle:
        def grade(self, record, ground_truth):
            raise _Boom("oracle-crashed")

    suite_raising = Suite(
        name="halt_suite",
        version="v1",
        cases=cases,
        arms=arms,
        oracle=_RaisingOracle(),
        control_arm="halt_arm",
        primary_metric="text_match",
        null_rule="none",
    )

    def _classify(exc: BaseException) -> tuple[str, bool]:
        if isinstance(exc, _Boom):
            return ("data_bug", True)
        return ("unknown", True)

    try:
        await run_suite_with_salvage(
            suite_raising, tmp_path / "halt", trials=1, classify_exception=_classify
        )
    except _Boom as exc:
        assert "oracle-crashed" in str(exc)
    else:
        raise AssertionError("halt classifier must re-raise the original exception")


async def test_classified_flake_continues_sweep(tmp_path: Path):
    """A cell that raises but the classifier tags as (`flake`, halt=False) becomes an ERROR
    outcome; sibling cells still run to completion. The sweep does not throw away hours of
    completed work on one flake."""

    class _Boom(RuntimeError):
        pass

    def _flake_arm(name: str) -> Arm:
        def _build(case: Case) -> api.Topology:
            text = str(case.payload["text"])

            def topo(b):
                async def _e(_inp):
                    yield _Answer(text=text)

                b.producer_kind("e", schemas=[_Answer], schema_version=1, factory=lambda: _e)
                b.initial("e", input=None)
                b.termination(api.threshold_count("substrate.ProducerCompleted", 1))

            return topo

        return Arm(name=name, role="full", build=_build)

    # Even a raise inside the Producer becomes ProducerFailed inside Runtime (Runtime catches
    # Exception at the task boundary). So we drive the flake path via a raising oracle.
    class _RaisingOracle:
        def grade(self, record, ground_truth):
            if any(e["kind"] == "_Answer" and e["payload"]["text"] == "raise" for e in record):
                raise _Boom("flake")
            return LogProjectionOracle(extract=lambda es: "ok", metric="m").grade(
                record, ground_truth
            )

    # c2 payload asks the oracle to raise; c1 grades cleanly.
    cases = (
        Case(case_id="c1", payload={"text": "ok"}, ground_truth="ok"),
        Case(case_id="c2", payload={"text": "raise"}, ground_truth="ok"),
    )
    arms = (_flake_arm("a1"),)
    suite = Suite(
        name="flake_suite",
        version="v1",
        cases=cases,
        arms=arms,
        oracle=_RaisingOracle(),
        control_arm="a1",
        primary_metric="m",
        null_rule="none",
    )

    def _classify(exc: BaseException) -> tuple[str, bool]:
        return ("flake", False)

    outcomes = await run_suite_with_salvage(
        suite, tmp_path / "flake", trials=1, classify_exception=_classify
    )
    outcomes_by_case = {o.case.case_id: o for o in outcomes}
    assert outcomes_by_case["c1"].source is CellSource.RUN
    assert outcomes_by_case["c2"].source is CellSource.ERROR
    assert outcomes_by_case["c2"].exception_reason == "flake"
    assert outcomes_by_case["c2"].halt is False


async def test_per_cell_budget_timeout_becomes_error_outcome(tmp_path: Path):
    """A cell wrapped in a 0.05s PerCellBudget on a producer that sleeps 1s trips
    `asyncio.wait_for`, the classifier maps TimeoutError to (`timed_out`, False), and
    the outcome is ERROR with a real elapsed exception."""

    async def _slow_producer():
        async def _s(_inp):
            await asyncio.sleep(1.0)
            yield _Answer(text="never")

        return _s

    def _slow_arm(name: str) -> Arm:
        def _build(case: Case) -> api.Topology:
            def topo(b):
                async def _s(_inp):
                    await asyncio.sleep(1.0)
                    yield _Answer(text="never")

                b.producer_kind("s", schemas=[_Answer], schema_version=1, factory=lambda: _s)
                b.initial("s", input=None)
                b.termination(api.threshold_count("substrate.ProducerCompleted", 1))

            return topo

        return Arm(name=name, role="full", build=_build)

    cases = (Case(case_id="c1", payload={"text": "x"}, ground_truth="x"),)
    arms = (_slow_arm("slow"),)
    suite = Suite(
        name="slow_suite",
        version="v1",
        cases=cases,
        arms=arms,
        oracle=_text_oracle(),
        control_arm="slow",
        primary_metric="m",
        null_rule="none",
    )

    def _budget(_a, _c) -> PerCellBudget:
        return PerCellBudget(time_s=0.05, reason="test-timeout")

    def _classify(exc: BaseException) -> tuple[str, bool]:
        if isinstance(exc, (TimeoutError, asyncio.TimeoutError)):
            return ("timed_out", False)
        return ("unknown", True)

    outcomes = await run_suite_with_salvage(
        suite,
        tmp_path / "slow",
        trials=1,
        budget_for_cell=_budget,
        classify_exception=_classify,
    )
    assert len(outcomes) == 1
    o = outcomes[0]
    assert o.source is CellSource.ERROR
    assert o.exception_reason == "timed_out"
    assert o.budget is not None
    assert o.budget.time_s == 0.05
    assert o.budget.reason == "test-timeout"


async def test_on_outcome_hook_fires_exactly_once_per_cell(tmp_path: Path):
    """`on_outcome` is awaited once per completed cell (RUN + SALVAGE + ERROR alike) under
    the loop's lock so a runner can append a JSONL row atomically."""
    suite = _suite([("c1", "a"), ("c2", "b"), ("c3", "c")], ["a1"])
    seen: list[CellOutcome] = []

    async def _hook(o: CellOutcome) -> None:
        seen.append(o)

    outcomes = await run_suite_with_salvage(suite, tmp_path / "hook", trials=1, on_outcome=_hook)
    assert len(seen) == 3
    assert {o.case.case_id for o in seen} == {"c1", "c2", "c3"}
    assert len(outcomes) == 3


async def test_skip_bypasses_triple(tmp_path: Path):
    """`skip(arm, case, trial)=True` means the triple never enters the sweep. Returned
    outcomes contain only the non-skipped triples."""
    suite = _suite([("c1", "a"), ("c2", "b"), ("c3", "c")], ["a1"])

    def _skip(_a: Arm, case: Case, _t: int) -> bool:
        return case.case_id == "c2"

    outcomes = await run_suite_with_salvage(suite, tmp_path / "skip", trials=1, skip=_skip)
    assert len(outcomes) == 2
    assert {o.case.case_id for o in outcomes} == {"c1", "c3"}


async def test_concurrency_caps_parallel_cells(tmp_path: Path):
    """The semaphore caps at `concurrency`; observing >2 concurrent cells with a limit of 2
    would violate the contract. A slow producer that reports its own concurrent count via a
    shared list proves the cap holds."""
    counter = {"live": 0, "max": 0}

    async def _observer():
        async def _o(_inp):
            counter["live"] += 1
            counter["max"] = max(counter["max"], counter["live"])
            await asyncio.sleep(0.05)
            counter["live"] -= 1
            yield _Answer(text="ok")

        return _o

    def _observed_arm(name: str) -> Arm:
        def _build(case: Case) -> api.Topology:
            def topo(b):
                async def _o(_inp):
                    counter["live"] += 1
                    counter["max"] = max(counter["max"], counter["live"])
                    await asyncio.sleep(0.05)
                    counter["live"] -= 1
                    yield _Answer(text="ok")

                b.producer_kind("o", schemas=[_Answer], schema_version=1, factory=lambda: _o)
                b.initial("o", input=None)
                b.termination(api.threshold_count("substrate.ProducerCompleted", 1))

            return topo

        return Arm(name=name, role="full", build=_build)

    cases = tuple(Case(case_id=f"c{i}", payload={"text": "x"}, ground_truth="ok") for i in range(6))
    arms = (_observed_arm("a1"),)
    suite = Suite(
        name="conc",
        version="v1",
        cases=cases,
        arms=arms,
        oracle=_text_oracle(),
        control_arm="a1",
        primary_metric="m",
        null_rule="none",
    )

    await run_suite_with_salvage(suite, tmp_path / "conc", trials=1, concurrency=2)
    assert counter["max"] <= 2, f"observed {counter['max']} concurrent cells, cap was 2"


async def test_default_classifier_halts_on_any_exception(tmp_path: Path):
    """No classifier passed = every exception halts (the conservative default). A
    runner opts into flake-continue by supplying a classifier; the library never
    silently paper-overs an exception."""

    class _Boom(RuntimeError):
        pass

    class _RaisingOracle:
        def grade(self, record, ground_truth):
            raise _Boom("plain")

    cases = (Case(case_id="c1", payload={"text": "x"}, ground_truth="x"),)
    arms = (_make_arm("a1"),)
    suite = Suite(
        name="halt_default",
        version="v1",
        cases=cases,
        arms=arms,
        oracle=_RaisingOracle(),
        control_arm="a1",
        primary_metric="m",
        null_rule="none",
    )

    try:
        await run_suite_with_salvage(suite, tmp_path / "hd", trials=1)
    except _Boom:
        pass
    else:
        raise AssertionError("default classifier must halt on any exception")
