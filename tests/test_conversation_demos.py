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
