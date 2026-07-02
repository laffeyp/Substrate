"""Observation contract for the reproduction-test generator (sprint 144): the fence-stripping parser, the
producer emitting a ReproductionTest, and the death-catch (a model error -> empty test, not a wedge)."""

from substrate import api
from substrate.api import Runtime, read_record
from substrate.reference._models import DeterministicResponder, ModelUsage, Responder
from substrate.topologies.swebench_solver.records import ReproductionTest
from substrate.topologies.swebench_solver.reproduction import (
    parse_repro_code,
    repro_generator_factory,
)


def test_parse_repro_code_strips_fences() -> None:
    assert parse_repro_code("```python\nprint('Issue resolved')\n```") == "print('Issue resolved')"
    assert parse_repro_code("print('x')") == "print('x')"  # no fence, unchanged


async def _run(tmp_path, responder: Responder, issue: str) -> list[dict]:  # type: ignore[no-untyped-def]
    def topo(b: api.TopologyBuilder) -> None:
        b.producer_kind(
            "repro",
            schemas=[ReproductionTest, ModelUsage],
            schema_version=1,
            factory=repro_generator_factory(responder, issue),
            deterministic=False,
        )
        b.initial("repro", input=None)
        b.termination(
            api.any_of(
                api.threshold_count("ReproductionTest", 1), api.quiescence_with_watchdog(seconds=5)
            )
        )

    await Runtime(tmp_path / "run").run(topo)
    return list(read_record(tmp_path / "run"))


async def test_repro_generator_emits_the_test(tmp_path) -> None:  # type: ignore[no-untyped-def]
    responder = DeterministicResponder(
        seed=0, menu=["```python\nassert True\nprint('Issue resolved')\n```"]
    )
    events = await _run(tmp_path, responder, "f returns the wrong value")
    repro = [e["payload"] for e in events if e["kind"] == "ReproductionTest"]
    assert (
        len(repro) == 1 and "Issue resolved" in repro[0]["code"] and "```" not in repro[0]["code"]
    )


class _DyingResponder:
    def respond(self, prompt: str) -> str:
        raise RuntimeError("model died")


async def test_repro_generator_handles_a_failed_model_call(tmp_path) -> None:  # type: ignore[no-untyped-def]
    events = await _run(tmp_path, _DyingResponder(), "issue text")
    repro = [e["payload"] for e in events if e["kind"] == "ReproductionTest"]
    assert (
        len(repro) == 1 and repro[0]["code"] == ""
    )  # empty test on a failed call; the run still finishes


async def test_repro_generator_meters(tmp_path) -> None:  # type: ignore[no-untyped-def]
    responder = DeterministicResponder(seed=0, menu=["print('Issue reproduced')"])
    events = await _run(tmp_path, responder, "issue")
    assert any(e["kind"] == "ModelUsage" for e in events)  # the model call is metered (#3)
