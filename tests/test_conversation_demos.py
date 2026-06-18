"""Conversation demos — CI-mode wiring tests (Wave 13).

Each demo (debate / prisoner's dilemma / intel asymmetry) is the conversation substrate plus a
set of speaker prompts; CI mode proves the wiring runs deterministically and finalises. The
real dynamics (the demonstration) are the walkthrough against local LLMs.
"""

import pytest

from substrate.api import Runtime, first_divergence, read_record
from substrate.topologies.conversation_demos import (
    debate_topology,
    intel_asymmetry_topology,
    prisoners_dilemma_topology,
)


@pytest.mark.timeout(15)
async def test_debate_runs_round_robin(tmp_path):
    await Runtime(tmp_path / "run").run(debate_topology(max_rounds=3))
    envs = list(read_record(tmp_path / "run"))
    turns = [e for e in envs if e["kind"] == "Turn"]
    assert len(turns) == 6  # 2 advocates x 3 rounds
    assert envs[-1]["kind"] == "substrate.RunFinalised"


@pytest.mark.timeout(15)
async def test_prisoners_dilemma_one_shot(tmp_path):
    # one round: ALPHA reasons (r1), BRAVO decides (r1), done.
    result = await Runtime(tmp_path / "run").run(prisoners_dilemma_topology(max_rounds=1))
    assert result.status == "finalised"
    turns = [e for e in read_record(tmp_path / "run") if e["kind"] == "Turn"]
    assert [(t["payload"]["speaker"], t["payload"]["round"]) for t in turns] == [(1, 1), (2, 1)]


@pytest.mark.timeout(15)
async def test_intel_asymmetry_runs_and_is_deterministic(tmp_path):
    await Runtime(tmp_path / "a").run(intel_asymmetry_topology(max_rounds=3))
    await Runtime(tmp_path / "b").run(intel_asymmetry_topology(max_rounds=3))
    assert first_divergence(tmp_path / "a", tmp_path / "b") is None  # D-8 log-equivalence
    turns = [e for e in read_record(tmp_path / "a") if e["kind"] == "Turn"]
    assert len(turns) == 6


# ── per-game CLAIM predicates (the outcome is on the record, not in prose) ──────
# These are the SAME predicates the real-model demo suite runs (tests/test_realmodel_demos.py); here
# they assert the claim is RECORD-ASSERTABLE in CI (the wiring), there against a live model (the claim).


@pytest.mark.timeout(15)
async def test_prisoners_dilemma_decision_is_on_the_record(tmp_path):
    # PD's claim is the OUTCOME (who defected), and it must be a record assertion, not a reading of
    # the prose. The detector emits one Decision{prisoner, choice} per prisoner.
    await Runtime(tmp_path / "run").run(prisoners_dilemma_topology(max_rounds=1))
    decisions = [e["payload"] for e in read_record(tmp_path / "run") if e["kind"] == "Decision"]
    assert {d["prisoner"] for d in decisions} == {1, 2}  # both prisoners' choices recorded
    assert all(d["choice"] in {"silent", "talk"} for d in decisions)  # the outcome is typed, readable


@pytest.mark.timeout(15)
async def test_intel_asymmetry_jointcall_is_on_the_record(tmp_path):
    # intel's claim is a calibrated JOINT CALL; the detector emits JointCall{analyst, assessment,
    # confidence} so "they reached a calibrated assessment" is record-derivable, not prose.
    await Runtime(tmp_path / "run").run(intel_asymmetry_topology(max_rounds=3))
    calls = [e["payload"] for e in read_record(tmp_path / "run") if e["kind"] == "JointCall"]
    assert calls, "no JointCall recorded — the joint assessment is not on the log"
    assert all(0 <= c["confidence"] <= 100 for c in calls)  # calibrated confidence is typed
    assert all(c["assessment"] in {"offensive", "routine", "uncertain"} for c in calls)
