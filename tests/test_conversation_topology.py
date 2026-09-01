# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Conversation topology — CI structural + pressure tests (Wave 13).

The N-speaker turn-based substrate under debate / prisoner's dilemma / intel asymmetry:
round-robin turns to a budget, deterministic, with a converge-early-stop and the same
liveness/determinism guarantees the Wave-11 topologies hold.
"""

import pytest

from substrate.api import Runtime, assert_replayable, first_divergence, read_record
from substrate.reference._models import DeterministicResponder
from substrate.topologies.conversation import conversation_topology


def _responders(n: int) -> list[DeterministicResponder]:
    return [DeterministicResponder(seed=i) for i in range(n)]


@pytest.mark.timeout(15)
async def test_round_robin_runs_to_budget(tmp_path):
    topo = conversation_topology(_responders(2), max_rounds=3)
    result = await Runtime(tmp_path / "run").run(topo)
    assert result.status == "finalised"
    envs = list(read_record(tmp_path / "run"))
    turns = [e for e in envs if e["kind"] == "Turn"]
    assert len(turns) == 6  # 2 speakers x 3 rounds
    # strict round-robin order: (s1,r1),(s2,r1),(s1,r2),(s2,r2),(s1,r3),(s2,r3)
    seq = [(t["payload"]["speaker"], t["payload"]["round"]) for t in turns]
    assert seq == [(1, 1), (2, 1), (1, 2), (2, 2), (1, 3), (2, 3)]
    assert envs[-1]["kind"] == "substrate.RunFinalised"


@pytest.mark.timeout(15)
async def test_convergence_stops_early(tmp_path):
    # speaker 1 declares convergence in round 2 -> the cascade stops, threshold_count finalises.
    topo = conversation_topology(_responders(2), max_rounds=5, converge_at=(1, 2))
    result = await Runtime(tmp_path / "run").run(topo)
    assert result.status == "finalised"
    envs = list(read_record(tmp_path / "run"))
    turns = [e for e in envs if e["kind"] == "Turn"]
    converged = [e for e in envs if e["kind"] == "Converged"]
    # (s1,r1),(s2,r1) then speaker-1 converges at r2 instead of a Turn
    assert [(t["payload"]["speaker"], t["payload"]["round"]) for t in turns] == [(1, 1), (2, 1)]
    assert len(converged) == 1 and converged[0]["payload"]["by"] == 1
    assert envs[-1]["kind"] == "substrate.RunFinalised"


@pytest.mark.timeout(15)
async def test_n_speakers_round_robin(tmp_path):
    topo = conversation_topology(_responders(3), max_rounds=2)
    await Runtime(tmp_path / "run").run(topo)
    envs = list(read_record(tmp_path / "run"))
    seq = [(e["payload"]["speaker"], e["payload"]["round"]) for e in envs if e["kind"] == "Turn"]
    assert seq == [(1, 1), (2, 1), (3, 1), (1, 2), (2, 2), (3, 2)]  # 3 x 2, wraps 3->1 at round++


@pytest.mark.timeout(15)
async def test_conversation_is_deterministic_and_replays_level_2(tmp_path):
    def build():
        return conversation_topology(_responders(2), max_rounds=3)

    await Runtime(tmp_path / "a").run(build())
    await Runtime(tmp_path / "b").run(build())
    assert first_divergence(tmp_path / "a", tmp_path / "b") is None  # D-8 log-equivalence
    result = assert_replayable(tmp_path / "a", "2")
    assert result.decisions_verified > 0 and not result.mismatches
