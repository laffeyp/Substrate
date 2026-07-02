"""Real-model coverage for the assay layer's model-bearing path (Ollama present).

The rest of the assay suite is deterministic CI (a stand-in responder), which proves the WIRING. The
one thing a stand-in cannot show is whether the metered seam captures a REAL provider's token/latency
accounting and lands it on the record as provider-truth (estimated=False) — the Sprint-1 review flagged
exactly this as "the metered glue CI can't see". These run the live local model and assert it from the
record, never from the model's words.

GATING (the repo convention): a required model ABSENT -> SKIP (names the model); model PRESENT but the
claim FAILS -> HARD FAIL (the seam did not work). Run as part of `uv run pytest`; deselect with
`pytest -m "not realmodel"`.
"""

from __future__ import annotations

import pytest
from msgspec import Struct

from substrate import api
from substrate.assay import (
    BASELINE,
    PASS,
    Arm,
    Case,
    LogProjectionOracle,
    Suite,
    build_report,
    run_suite,
)
from substrate.reference._models import ModelUsage, OllamaResponder, call_responder_metered

pytestmark = pytest.mark.realmodel

_OLLAMA_V1 = "http://localhost:11434/v1"
_MODEL = (
    "qwen2.5:7b-instruct"  # a capable local model (a 128GB M5 runs the 7B/8B locals comfortably)
)


def _require(*models: str) -> None:
    try:
        import httpx

        ids = {m["id"] for m in httpx.get(_OLLAMA_V1 + "/models", timeout=4).json().get("data", [])}
    except Exception as exc:  # noqa: BLE001 - any unreachability is a SKIP
        pytest.skip(f"real-model assay skipped — Ollama not reachable ({type(exc).__name__})")
    missing = [m for m in models if m not in ids]
    if missing:
        pytest.skip(f"real-model assay skipped — model(s) absent: {', '.join(missing)}")


@pytest.mark.timeout(120)
async def test_metered_seam_captures_real_provider_accounting():
    # the metered seam against a LIVE model: the usage must be provider-truth (estimated=False) with
    # real, non-zero token counts and inference latency — the thing the deterministic stand-in fakes.
    _require(_MODEL)
    r = OllamaResponder(_MODEL, max_tokens=64)
    text, usage = await call_responder_metered(
        r, "In one short sentence, what is an append-only log?"
    )
    assert usage.estimated is False, (
        f"metered seam did not mark live usage as provider truth: {usage}"
    )
    assert usage.prompt_tokens > 0, f"no real prompt tokens from the provider: {usage}"
    assert usage.completion_tokens > 0, f"no real completion tokens from the provider: {usage}"
    assert usage.wall_ms > 0, f"no real inference latency from the provider: {usage}"
    assert usage.model == _MODEL
    assert text.strip(), "the live model returned empty content"


class _Answer(Struct, frozen=True):
    text: str


def _real_metered_topology(model_name: str):  # noqa: ANN201
    """A one-Producer topology that calls the metered seam against a REAL model and emits its usage +
    answer onto the record — the shape an assay arm uses to land real provider accounting on its run."""

    def _factory():  # noqa: ANN202
        async def producer(_inp):  # noqa: ANN001, ANN202
            r = OllamaResponder(model_name, max_tokens=32)
            text, usage = await call_responder_metered(r, "Reply with a single word: ready")
            yield usage
            yield _Answer(text=text)

        return lambda: producer

    def topo(b: api.TopologyBuilder) -> None:
        b.producer_kind(
            "answerer",
            schemas=[ModelUsage, _Answer],
            schema_version=1,
            factory=_factory(),
            deterministic=False,  # a real model is not author-deterministic
        )
        b.initial("answerer", input=None)
        b.termination(api.all_completed())

    return topo


@pytest.mark.timeout(180)
async def test_assay_aggregates_real_usage_end_to_end(tmp_path):
    # a REAL model driven through the WHOLE assay layer (run_suite -> grade -> build_report), asserting
    # its provider usage (estimated=False) was aggregated into the Report — the metered seam -> record
    # -> report path on a live model, which no deterministic test can demonstrate.
    _require(_MODEL)

    def _produced_answer(envelopes):  # noqa: ANN001, ANN202
        finals = [e for e in envelopes if e["kind"] == "_Answer"]
        return bool(finals and str(finals[-1]["payload"]["text"]).strip())

    suite = Suite(
        name="realmodel-smoke",
        version="0.1",
        cases=(Case("c1", {}, True),),
        arms=(
            Arm(name="baseline", role=BASELINE, build=lambda case: _real_metered_topology(_MODEL)),
        ),
        oracle=LogProjectionOracle(extract=_produced_answer, metric="produced_answer"),
        control_arm="baseline",
        primary_metric="produced_answer",
        null_rule="n/a (smoke test, single arm)",
    )
    results = await run_suite(suite, tmp_path, trials=1)
    report = build_report(suite, results)
    arm = report.arms[0]
    assert report.control_check.state == PASS
    assert arm.model_calls >= 1, "no model call landed on the record"
    assert arm.completion_tokens > 0, "no real completion tokens aggregated into the report"
    assert arm.estimated_usage is False, "real provider usage was mislabeled as a stand-in estimate"
