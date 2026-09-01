# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Recursive decomposition topology — CI MODE structural tests (Sprint 132).

Deterministic planner + solvers, asserting: ONE Trigger spawns solvers at every depth (the
recursive-Trigger property), depth is carried correctly down the tree, and the depth budget
contains a runaway solver on the log (DepthBudgetExceeded), bounding the recursion.
"""

import pytest

from substrate.api import Runtime, read_record
from substrate.reference._models import DeterministicResponder
from substrate.topologies.recursive_decomposition import recursive_decomposition_topology


def _topo(*, max_depth=2, fanout=2, runaway=False):
    return recursive_decomposition_topology(
        "build a feature",
        solver_model=DeterministicResponder(seed=3),
        max_depth=max_depth,
        fanout=fanout,
        runaway=runaway,
        deterministic=True,
    )


@pytest.mark.timeout(15)
async def test_single_trigger_handles_all_depths(tmp_path):
    # max_depth=2, fanout=2: planner -> 2 subtasks@1; spawn-solver fires 2 solvers@1 (each ->
    # 2 subtasks@2); spawn-solver fires 4 solvers@2 (leaves). 6 SubtaskProposed, 6 solver spawns
    # — all from ONE Trigger id, at two different depths (the recursive-Trigger property).
    result = await Runtime(tmp_path / "run").run(_topo())
    assert result.status == "finalised"
    envs = list(read_record(tmp_path / "run"))
    spawn_fires = [
        e
        for e in envs
        if e["kind"] == "substrate.TriggerFired"
        and e["payload"].get("trigger_id") == "spawn-solver"
    ]
    solver_starts = [
        e
        for e in envs
        if e["kind"] == "substrate.ProducerStarted" and e["payload"]["producer"]["kind"] == "solver"
    ]
    assert len(spawn_fires) == 6
    assert len(solver_starts) == 6
    # the one trigger fired at both depth 1 and depth 2 (resolved input carries the depth)
    fired_depths = {f["payload"]["resolved_input"]["depth"] for f in spawn_fires}
    assert fired_depths == {1, 2}
    assert envs[-1]["kind"] == "substrate.RunFinalised"


@pytest.mark.timeout(15)
async def test_ancestry_depth_correctly_computed(tmp_path):
    await Runtime(tmp_path / "run").run(_topo())
    envs = list(read_record(tmp_path / "run"))
    proposed = [e for e in envs if e["kind"] == "SubtaskProposed"]
    depths = sorted(e["payload"]["depth"] for e in proposed)
    assert depths == [1, 1, 2, 2, 2, 2]  # 2 roots@1, each fanning to 2 @2
    # children name their parent; the depth-2 subtasks descend from the depth-1 ones
    by_depth = {1: [], 2: []}
    for e in proposed:
        by_depth[e["payload"]["depth"]].append(e["payload"])
    assert all(p["parent_task_id"] is None for p in by_depth[1])
    assert all(p["parent_task_id"] is not None for p in by_depth[2])
    # only the deepest solvers (depth == max_depth) solve; 4 leaves -> 4 solutions
    solutions = [e for e in envs if e["kind"] == "SolutionReached"]
    assert len(solutions) == 4


@pytest.mark.timeout(15)
async def test_depth_budget_prevents_overflow(tmp_path):
    # runaway solvers ALWAYS decompose, ignoring the budget. The depth-budget Trigger must catch
    # every subtask proposed beyond max_depth and fire the guard (DepthBudgetExceeded) instead of
    # a solver — so no solver ever starts at depth > max_depth.
    await Runtime(tmp_path / "run").run(_topo(runaway=True))
    envs = list(read_record(tmp_path / "run"))
    exceeded = [e for e in envs if e["kind"] == "DepthBudgetExceeded"]
    assert exceeded, "a runaway recursion must trip the depth budget on the log"
    assert all(e["payload"]["depth"] == 3 and e["payload"]["budget"] == 2 for e in exceeded)
    # no solver spawned for an over-budget subtask: every spawn-solver firing is within budget
    spawn_fires = [
        e
        for e in envs
        if e["kind"] == "substrate.TriggerFired"
        and e["payload"].get("trigger_id") == "spawn-solver"
    ]
    assert all(f["payload"]["resolved_input"]["depth"] <= 2 for f in spawn_fires)


@pytest.mark.timeout(15)
async def test_runaway_recursion_terminates_via_budget(tmp_path):
    # the adversarial guarantee: even with solvers trying to recurse forever, the run TERMINATES
    # (does not hang) because the budget boundary stops the spawn — bounded by the topology.
    result = await Runtime(tmp_path / "run").run(_topo(max_depth=2, runaway=True))
    assert result.status == "finalised"
    envs = list(read_record(tmp_path / "run"))
    # the deepest subtasks proposed are at max_depth+1, and none of them spawned a solver
    proposed_depths = [e["payload"]["depth"] for e in envs if e["kind"] == "SubtaskProposed"]
    assert max(proposed_depths) == 3
    solver_depths = [
        f["payload"]["resolved_input"]["depth"]
        for f in envs
        if f["kind"] == "substrate.TriggerFired"
        and f["payload"].get("trigger_id") == "spawn-solver"
    ]
    assert max(solver_depths) == 2  # no solver ran at depth 3
    assert envs[-1]["kind"] == "substrate.RunFinalised"
