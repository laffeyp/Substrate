"""Observation contract for delegate (sprint 141, workflow-parity W2.1).

CI, deterministic, no network: a parent tool_loop scripted to call `delegate` once; the child is the
built-in calculator agent ((2+3)*4 = 20), pure and reproducible. Asserts the child runs as its OWN record,
the answer folds back into the parent's ToolResult, the parent's result cites the child root
(run-granularity provenance), and the depth/fan-out caps refuse with typed failures.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from substrate import api
from substrate.topologies.tool_loop import tool_loop_topology
from substrate.topologies.tool_loop.delegate import make_delegate
from substrate.topologies.tool_loop.tools import full_suite, ollama_tools, parse_tool_call


def _calculator_child(task: str, child_root: Path) -> object:
    # the built-in calculator agent: add(2,3) -> mul(5,4) -> answer "20". Pure -> the child record is
    # deterministic. Stands in for "a real sub-agent" while keeping CI byte-reproducible.
    return tool_loop_topology(max_steps=4)


def test_delegate_runs_a_child_and_folds_the_answer_back(tmp_path: Path) -> None:
    delegate = make_delegate(child_factory=_calculator_child, root=tmp_path)
    parent = tool_loop_topology(
        script=[("delegate", ["compute (2+3)*4"])],  # the parent's one move: hand it off
        tools={"delegate": delegate},
        max_steps=3,
    )
    result = asyncio.run(api.Runtime(tmp_path / "parent").run(parent))
    events = list(api.read_record(tmp_path / "parent"))
    kinds = [e["kind"] for e in events]

    assert result.status == "finalised"
    assert "ToolCall" in kinds and "ToolResult" in kinds and "FinalAnswer" in kinds
    tr = next(e for e in events if e["kind"] == "ToolResult")
    assert tr["payload"]["ok"] is True  # the child ran without error
    out = tr["payload"]["output"]
    assert out["answer"] == "20"  # the calculator child's answer folded back
    assert out["steps"] >= 1

    # run-granularity provenance: the parent's ToolResult names the child record root, and it is a real,
    # complete record (the child is citable from the parent — composition.py §20's guarantee).
    child_root = Path(out["child_root"])
    child_kinds = [e["kind"] for e in api.read_record(child_root)]
    assert child_kinds[-1] == "substrate.RunFinalised"
    assert child_kinds.count("FinalAnswer") == 1

    # no invented vocabulary on the parent — delegate is a tool, its result is an ordinary ToolResult
    known = {"ToolCall", "ToolResult", "FinalAnswer"}
    assert not any(k not in known and not k.startswith("substrate.") for k in kinds)


def test_delegate_is_visible_and_callable_via_native_tool_calling(tmp_path: Path) -> None:
    # regression (walkthrough-caught): the scripted CI path calls delegate DIRECTLY, bypassing tool
    # presentation. A real model traverses ollama_tools (the schema list it is shown) + parse_tool_call
    # (mapping its reply back to positional args). A walkthrough found delegate invisible there — no
    # schema entry, so ollama_tools dropped it and its args were unmappable. Assert the real path.
    suite = {**full_suite(tmp_path), "delegate": make_delegate(child_factory=_calculator_child, root=tmp_path)}
    names = {t["function"]["name"] for t in ollama_tools(suite)}
    assert "delegate" in names  # the model is actually shown the tool
    msg = {"tool_calls": [{"function": {"name": "delegate", "arguments": {"task": "do X"}}}]}
    kind, chosen = parse_tool_call(msg, suite)
    assert kind == "tool" and chosen == ("delegate", ["do X"])  # its task arg is mapped, not dropped


def test_depth_cap_refuses_instead_of_recursing(tmp_path: Path) -> None:
    # a delegate already at the chain limit must refuse — the guard against unbounded delegation
    at_limit = make_delegate(child_factory=_calculator_child, root=tmp_path, depth=2, max_depth=2)
    try:
        at_limit.run(["anything"])
        assert False, "expected a max-depth refusal"
    except ValueError as exc:
        assert "max delegation depth" in str(exc)


def test_fanout_cap_refuses_the_extra_child(tmp_path: Path) -> None:
    once = make_delegate(child_factory=_calculator_child, root=tmp_path, max_children=1)
    first = once.run(["first"])  # allowed
    assert first["answer"] == "20"
    try:
        once.run(["second"])  # over the fan-out cap
        assert False, "expected a max-children refusal"
    except ValueError as exc:
        assert "max children" in str(exc)


def test_a_cap_hit_surfaces_as_a_typed_result_through_the_loop_not_a_crash(tmp_path: Path) -> None:
    # a delegate cap is not just a raise in isolation — through the real loop it becomes a
    # ToolResult(ok=False) the parent model reads, exactly like any other tool failure (errors are
    # observations, never a crash). Parent delegates twice with max_children=1: first ok, second refused.
    parent = tool_loop_topology(
        script=[("delegate", ["first"]), ("delegate", ["second"])],
        tools={"delegate": make_delegate(child_factory=_calculator_child, root=tmp_path, max_children=1)},
        max_steps=4,
    )
    result = asyncio.run(api.Runtime(tmp_path / "p2").run(parent))
    events = list(api.read_record(tmp_path / "p2"))
    results = [e for e in events if e["kind"] == "ToolResult"]

    assert result.status == "finalised"
    assert results[0]["payload"]["ok"] is True  # first child ran and folded back
    assert results[1]["payload"]["ok"] is False  # second refused by the fan-out cap
    assert "max children" in results[1]["payload"]["error"]
