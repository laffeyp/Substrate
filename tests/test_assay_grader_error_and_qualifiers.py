"""Sprints 153 + 154 — Result.grader_error_band + ArmReport.model_ensemble_id/split_id.

Both are additive with safe defaults: existing callers unchanged. These tests lock (a) that the
fields round-trip through msgspec / dataclass construction; (b) that `build_report` stamps the
qualifiers on every ArmReport when passed; (c) that omitting them keeps existing behaviour.
"""

from __future__ import annotations

import pytest
from msgspec import Struct

from substrate import api
from substrate.assay import (
    BASELINE,
    FULL,
    Arm,
    Case,
    LogProjectionOracle,
    Result,
    Suite,
    build_report,
    run_suite,
)
from substrate.assay.oracle import LOG_PROJECTION, Verdict
from substrate.reference._models import DeterministicResponder, ModelUsage, call_responder_metered


def test_result_grader_error_band_defaults_none() -> None:
    r = Result(
        verdict=Verdict.PASS,
        score=1.0,
        metric="resolved",
        oracle_class="external-grader",
        replayable=False,
    )
    assert r.grader_error_band is None


def test_result_grader_error_band_round_trips() -> None:
    r = Result(
        verdict=Verdict.PASS,
        score=1.0,
        metric="resolved",
        oracle_class="external-grader",
        replayable=False,
        grader_error_band=0.078,
    )
    assert r.grader_error_band == pytest.approx(0.078)


def test_result_frozen_after_new_field() -> None:
    r = Result(
        verdict=Verdict.PASS,
        score=1.0,
        metric="m",
        oracle_class=LOG_PROJECTION,
        replayable=True,
        grader_error_band=0.02,
    )
    with pytest.raises((AttributeError, TypeError)):
        r.grader_error_band = 0.5  # type: ignore[misc]


class _Final(Struct, frozen=True):
    text: str


def _answer_topology(answer: str):
    responder = DeterministicResponder(seed=0)

    def _factory():
        async def producer(_inp):
            _text, usage = await call_responder_metered(responder, "decide")
            yield usage
            yield _Final(text=answer)

        return lambda: producer

    def topo(b: api.TopologyBuilder) -> None:
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


def _demo_suite() -> Suite:
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


async def test_arm_report_qualifiers_default_empty(tmp_path) -> None:
    suite = _demo_suite()
    results = await run_suite(suite, tmp_path, trials=1)
    report = build_report(suite, results)
    for arm in report.arms:
        assert arm.model_ensemble_id == ""
        assert arm.split_id == ""


async def test_arm_report_qualifiers_stamped_when_passed(tmp_path) -> None:
    suite = _demo_suite()
    results = await run_suite(suite, tmp_path, trials=1)
    report = build_report(
        suite,
        results,
        model_ensemble_id="kimi-k2.6+glm-5.1+nemotron-3-super",
        split_id="swebench-lite@2026-08-08",
    )
    for arm in report.arms:
        assert arm.model_ensemble_id == "kimi-k2.6+glm-5.1+nemotron-3-super"
        assert arm.split_id == "swebench-lite@2026-08-08"
