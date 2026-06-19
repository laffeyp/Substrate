"""Tests for the coding_flow topology — best-of-N codegen + build-validation + a correction loop.

The validator runs a REAL gate (ruff + mypy + pytest in a subprocess), so the run is not
replay-deterministic (verdict order tracks subprocess timing). These assert the OUTCOME — which
candidate the gate passes, which terminal the run reaches — which IS deterministic for the canned
candidates. The @realmodel test closes the loop with a real local coder + the real gate.
"""

import pytest

from substrate.api import Runtime, read_record
from substrate.topologies.coding_flow import (
    coding_flow_topology,
    ci_responders,
    walkthrough_responders,
)
from substrate.topologies.coding_flow.gate import parse_artifacts, run_gate
from substrate.topologies.coding_flow.task import CodingTask, kvstore_task

_OLLAMA_V1 = "http://localhost:11434/v1"
_CODERS = [
    "qwen2.5-coder:7b",
    "qwen2.5-coder:3b",
    "qwen2.5:7b-instruct",
    "llama3.1:8b",
    "llama3.2:3b",
]


def _outcome(events: list[dict]) -> dict | None:
    return next((e for e in events if e["kind"] in ("Solved", "Exhausted")), None)


def _kinds(events: list[dict], kind: str) -> list[dict]:
    return [e["payload"] for e in events if e["kind"] == kind]


# ── the deterministic gate core (no topology, no model) ─────────────────────────


def test_gate_discriminates_good_from_buggy() -> None:
    task = kvstore_task()
    good = run_gate({**task.fixtures, **parse_artifacts(task.ci_good)}, task.gate)
    bad = run_gate({**task.fixtures, **parse_artifacts(task.ci_bad)}, task.gate)
    assert good.passed and good.returncode == 0
    # the buggy candidate is ruff/mypy-clean but behaviourally wrong — only running the tests catches it
    assert not bad.passed
    assert "failed" in bad.summary.lower() or "passed" in bad.summary


def test_parse_artifacts_extracts_each_file() -> None:
    arts = parse_artifacts(kvstore_task().ci_good)
    assert set(arts) == {"store.py", "router.py"}
    assert "class Store" in arts["store.py"] and "def handle" in arts["router.py"]


def test_no_artifacts_fails_the_gate_without_crashing() -> None:
    r = run_gate(parse_artifacts("the model said nothing useful"), "true")
    assert not r.passed  # empty payloads -> a clean fail, not an exception


# ── the topology in CI mode (deterministic OUTCOME) ─────────────────────────────


async def test_best_of_n_validates_all_then_selects_the_passing_one(tmp_path) -> None:
    task = kvstore_task()
    topo = coding_flow_topology(task, responders=ci_responders(task, 3), n=3, max_rounds=2)
    await Runtime(tmp_path / "run").run(topo)
    events = list(read_record(tmp_path / "run"))

    verdicts = _kinds(events, "Verdict")
    assert len(verdicts) == 3  # the full best-of-N comparison is on the record before selection
    assert sum(v["passed"] for v in verdicts) == 1  # exactly one good candidate
    out = _outcome(events)
    assert out is not None and out["kind"] == "Solved"
    # selection tracks the gate, not a guess: the chosen slot's verdict actually passed
    assert any(v["slot"] == out["payload"]["slot"] and v["passed"] for v in verdicts)


class _CorrectingStub:
    """Buggy on the seed round; correct once it sees a gate failure in the prompt — drives the loop."""

    def __init__(self, task: CodingTask) -> None:
        self._task = task

    def respond(self, prompt: str) -> str:
        return self._task.ci_good if "FAILED the gate" in prompt else self._task.ci_bad


async def test_correction_loop_fixes_after_a_failed_round(tmp_path) -> None:
    task = kvstore_task()
    topo = coding_flow_topology(
        task, responders=[_CorrectingStub(task) for _ in range(3)], n=3, max_rounds=2
    )
    await Runtime(tmp_path / "run").run(topo)
    events = list(read_record(tmp_path / "run"))

    out = _outcome(events)
    assert out is not None and out["kind"] == "Solved"
    assert out["payload"]["round"] == 2  # round 1 all failed -> failures fed back -> round 2 passed
    assert len(_kinds(events, "Verdict")) == 6  # 3 candidates per round, both rounds on the record


async def test_exhausted_when_every_round_fails(tmp_path) -> None:
    task = kvstore_task()  # all stubs stay buggy with max_rounds=1 -> no correction round
    topo = coding_flow_topology(
        task, responders=[_CorrectingStub(task) for _ in range(3)], n=3, max_rounds=1
    )
    await Runtime(tmp_path / "run").run(topo)
    events = list(read_record(tmp_path / "run"))

    out = _outcome(events)
    assert out is not None and out["kind"] == "Exhausted"
    assert out["payload"]["rounds"] == 1
    assert all(not v["passed"] for v in _kinds(events, "Verdict"))


# ── walkthrough: a real local coder closes the loop against the real gate ───────


def _coder() -> str:
    try:
        import httpx

        ids = {m["id"] for m in httpx.get(_OLLAMA_V1 + "/models", timeout=4).json().get("data", [])}
    except Exception as exc:  # noqa: BLE001 - any unreachability is a SKIP
        pytest.skip(
            f"coding_flow walkthrough skipped — Ollama not reachable ({type(exc).__name__})"
        )
    for m in _CODERS:
        if m in ids:
            return m
    pytest.skip(f"coding_flow walkthrough skipped — no coder model among {_CODERS}")


@pytest.mark.realmodel
@pytest.mark.timeout(600)
async def test_walkthrough_real_coder_closes_the_loop(tmp_path) -> None:
    # the claim: a REAL local coder drafting + the REAL gate validating reaches a terminal — Solved if
    # any candidate's code actually passes ruff+mypy+pytest, else Exhausted after the rounds. Either
    # is a pass: it proves the loop closes on real model output, not that a 7B model is infallible.
    model = _coder()
    task = kvstore_task()
    topo = coding_flow_topology(
        task, responders=walkthrough_responders(model, n=3), n=3, max_rounds=2, timeout=180
    )
    await Runtime(tmp_path / "run").run(topo)
    events = list(read_record(tmp_path / "run"))

    assert _kinds(events, "Candidate"), "the real model produced at least one candidate"
    assert _kinds(events, "Verdict"), "each candidate was really gate-validated"
    out = _outcome(events)
    assert out is not None and out["kind"] in ("Solved", "Exhausted")
