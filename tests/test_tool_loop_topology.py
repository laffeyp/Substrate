"""Tool-using loop — CI structural + determinism tests (Wave 14).

Covers the three behaviors the loop is built around: the model -> tool -> model chain with the
result fed back in; a failed tool surfacing as a typed observation (not a crash); and the step
budget ending the run on a FinalAnswer rather than a silent stop.
"""

import pytest

from substrate.api import Runtime, first_divergence, read_record
from substrate.topologies.tool_loop import tool_loop_topology


@pytest.mark.timeout(15)
async def test_tool_loop_runs_to_final_answer(tmp_path):
    result = await Runtime(tmp_path / "run").run(tool_loop_topology())
    assert result.status == "finalised"
    envs = list(read_record(tmp_path / "run"))
    calls = [e for e in envs if e["kind"] == "ToolCall"]
    results = [e for e in envs if e["kind"] == "ToolResult"]
    finals = [e for e in envs if e["kind"] == "FinalAnswer"]
    # model -> tool -> model chain: add(2,3)=5, then mul(5,4)=20, then answer "20".
    assert [c["payload"]["tool"] for c in calls] == ["add", "mul"]
    assert [r["payload"]["output"] for r in results] == [5, 20]
    assert all(r["payload"]["ok"] for r in results)
    assert len(finals) == 1 and finals[0]["payload"]["text"] == "20"
    # the result was fed back: the second call multiplied the first tool's output, not a constant.
    assert calls[1]["payload"]["args"] == [5, 4]
    # the continue Trigger re-fired the model once per ToolResult, bounded — no runaway.
    continued = [
        e
        for e in envs
        if e["kind"] == "substrate.TriggerFired" and e["payload"].get("trigger_id") == "continue"
    ]
    assert len(continued) == 2
    assert envs[-1]["kind"] == "substrate.RunFinalised"


@pytest.mark.timeout(15)
async def test_failed_tool_is_an_observation_not_a_crash(tmp_path):
    # the model calls a tool that does not exist; the run must NOT crash — the failure comes back
    # as a typed ToolResult the model reads, and the model answers citing it.
    result = await Runtime(tmp_path / "run").run(
        tool_loop_topology(script=[("divide", [1, 0])])
    )
    assert result.status == "finalised"
    envs = list(read_record(tmp_path / "run"))
    bad = [e for e in envs if e["kind"] == "ToolResult" and not e["payload"]["ok"]]
    assert len(bad) == 1 and "unknown tool 'divide'" in bad[0]["payload"]["error"]
    finals = [e for e in envs if e["kind"] == "FinalAnswer"]
    assert len(finals) == 1 and "stopped" in finals[0]["payload"]["text"]
    # no Producer failed: the error stayed on the typed-event path, never an exception.
    assert not [e for e in envs if e["kind"] == "substrate.ProducerFailed"]


@pytest.mark.timeout(15)
async def test_step_budget_ends_on_a_final_answer(tmp_path):
    # a model that would never stop (always calls a tool) is capped at max_steps and the run still
    # ends cleanly on a FinalAnswer (the graceful-budget behavior), not a silent quiescence stop.
    result = await Runtime(tmp_path / "run").run(
        tool_loop_topology(script=[("add", [1, 1])] * 9, max_steps=3)
    )
    assert result.status == "finalised"
    envs = list(read_record(tmp_path / "run"))
    calls = [e for e in envs if e["kind"] == "ToolCall"]
    finals = [e for e in envs if e["kind"] == "FinalAnswer"]
    assert len(calls) == 3  # capped at the budget, not 9
    assert len(finals) == 1  # and it still produced a final answer
    assert envs[-1]["kind"] == "substrate.RunFinalised"


@pytest.mark.timeout(15)
async def test_tool_loop_is_deterministic(tmp_path):
    await Runtime(tmp_path / "a").run(tool_loop_topology())
    await Runtime(tmp_path / "b").run(tool_loop_topology())
    assert first_divergence(tmp_path / "a", tmp_path / "b") is None
