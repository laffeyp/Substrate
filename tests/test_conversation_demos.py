"""Conversation demos — CI-mode wiring tests (Wave 13).

Each demo (debate / prisoner's dilemma / intel asymmetry) is the conversation substrate plus a
set of speaker prompts; CI mode proves the wiring runs deterministically and finalises. The
real dynamics (the demonstration) are the walkthrough against local LLMs.
"""

import pytest

from substrate.api import Runtime, first_divergence, read_record
from substrate.topologies.debate import debate_topology
from substrate.topologies.intel_asymmetry import intel_asymmetry_topology
from substrate.topologies.prisoners_dilemma import prisoners_dilemma_topology


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
    # PD's claim is the OUTCOME (who defected), a record assertion not a reading of prose. The PRISONER
    # emits its own Decision{prisoner, choice} — and the record must ATTRIBUTE it to the prisoner, not
    # a parser (F-OBS-2). That provenance assertion is what catches the misattribution we just fixed.
    await Runtime(tmp_path / "run").run(prisoners_dilemma_topology(max_rounds=1))
    decisions = [e for e in read_record(tmp_path / "run") if e["kind"] == "Decision"]
    assert {e["payload"]["prisoner"] for e in decisions} == {1, 2}
    assert all(e["payload"]["choice"] in {"silent", "talk"} for e in decisions)
    # the author of prisoner N's Decision is speaker-N, not a detector:
    assert all(e["producer"]["kind"] == f"speaker-{e['payload']['prisoner']}" for e in decisions)


@pytest.mark.timeout(15)
async def test_intel_asymmetry_jointcall_is_on_the_record(tmp_path):
    # intel's claim is a calibrated JOINT CALL; the ANALYST emits JointCall{analyst, assessment,
    # confidence} itself, so the call is record-derivable AND attributed to the analyst (F-OBS-2).
    await Runtime(tmp_path / "run").run(intel_asymmetry_topology(max_rounds=3))
    calls = [e for e in read_record(tmp_path / "run") if e["kind"] == "JointCall"]
    assert calls, "no JointCall recorded — the joint assessment is not on the log"
    assert all(0 <= e["payload"]["confidence"] <= 100 for e in calls)
    assert all(e["payload"]["assessment"] in {"offensive", "routine", "uncertain"} for e in calls)
    assert all(e["producer"]["kind"] == f"speaker-{e['payload']['analyst']}" for e in calls)
