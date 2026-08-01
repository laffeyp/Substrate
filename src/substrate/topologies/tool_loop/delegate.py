"""delegate — a tool that hands a subtask to a CHILD agent and folds the answer back (workflow-parity W2.1).

The "subagent" the CLI products ship, on substrate: a tool-using agent calls `delegate(task)` mid-run;
a child agent runs the subtask to completion as its OWN replayable record; its answer folds back into the
parent's transcript as an ordinary ToolResult. The child record root rides on that result, so the parent
record cites the child — run-granularity provenance, the same guarantee `embedded_substrate` gives
(composition.py §20), reached through the tool result because the tool seam cannot mount a Producer.

WHY A THREAD. `tool_loop`'s `Tool.run` is synchronous and blocks the outer loop while it runs (`bash`
already does — `subprocess.run(timeout=60)`). A child substrate run is async. So the child runs to
completion in a worker thread hosting its own `asyncio.run`, and this tool blocks on it exactly as `bash`
blocks — no async contract is added to the tool seam. A concurrent child (running alongside the parent's
other work) would be the `embedded_substrate` Producer path instead; that is a separate, later shape.

CAPS. Depth (`max_depth`) bounds the delegation CHAIN; fan-out (`max_children`) bounds how many children
one delegate spawns. At either cap the tool returns a typed failure the model reads — never unbounded
recursion, never a silent spawn storm. A child that raises, produces no FinalAnswer, or runs past
`timeout_seconds` is a typed `ToolResult(ok=False)`, not a crash; the worker is a daemon so a timed-out
child cannot wedge process exit.
"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from ... import api
from ...adapters import Responder
from .tools import Tool, full_suite

# What the child IS, given a subtask and its own record root. Caller-supplied so delegate is agnostic to
# session-vs-named-topology, and CI can inject a deterministic child. Returns a topology builder callable.
ChildFactory = Callable[[str, Path], Callable[[api.TopologyBuilder], None]]


def _run_child_to_answer(
    topology: Callable[[api.TopologyBuilder], None],
    root: Path,
    *,
    timeout_seconds: float,
) -> tuple[str, int]:
    """Run `topology` to completion at `root` in a worker thread (its own event loop, isolated from the
    outer runtime's), then read the child's FinalAnswer off its record. Blocks the caller like `bash`.
    Raises TimeoutError / the child's exception / ValueError(no FinalAnswer) — the tool body turns any of
    these into a typed ToolResult the parent reads."""
    box: dict[str, Any] = {}

    def worker() -> None:
        try:
            box["result"] = asyncio.run(api.Runtime(root).run(topology))
        except BaseException as exc:  # carried back to the caller thread, not swallowed
            box["error"] = exc

    t = threading.Thread(target=worker, daemon=True)  # daemon: a hung child never blocks process exit
    t.start()
    t.join(timeout=timeout_seconds)
    if t.is_alive():
        raise TimeoutError(f"delegate child run exceeded {timeout_seconds}s")
    if "error" in box:
        raise box["error"]
    events = list(api.read_record(root))
    answer = next((e for e in events if e["kind"] == "FinalAnswer"), None)
    if answer is None:
        raise ValueError("delegate child produced no FinalAnswer")
    payload = answer["payload"]
    return str(payload.get("text", "")), int(payload.get("steps", 0))


def _default_child_factory(
    responder: Responder | None,
    walkthrough: bool,
    depth: int,
    max_depth: int,
    max_children: int,
    child_max_steps: int,
    timeout_seconds: float,
) -> ChildFactory:
    """The child is a real tool_loop agent over the full suite, plus a DEEPER delegate (depth+1) when the
    chain has room — so a delegated agent can itself delegate, bounded by max_depth."""
    from . import tool_loop_topology

    def factory(task: str, child_root: Path) -> Callable[[api.TopologyBuilder], None]:
        suite = full_suite(child_root)
        if depth + 1 < max_depth:
            suite = {
                **suite,
                "delegate": make_delegate(
                    responder=responder,
                    walkthrough=walkthrough,
                    root=child_root,
                    depth=depth + 1,
                    max_depth=max_depth,
                    max_children=max_children,
                    child_max_steps=child_max_steps,
                    timeout_seconds=timeout_seconds,
                ),
            }
        return tool_loop_topology(
            model=responder,
            task=task,
            tools=suite,
            walkthrough=walkthrough,
            max_steps=child_max_steps,
            deterministic=not walkthrough,
        )

    return factory


def make_delegate(
    *,
    child_factory: ChildFactory | None = None,
    responder: Responder | None = None,
    root: Path | str = ".",
    walkthrough: bool = False,
    depth: int = 0,
    max_depth: int = 2,
    max_children: int = 4,
    child_max_steps: int = 6,
    timeout_seconds: float = 120.0,
) -> Tool:
    """A `delegate` Tool the caller composes into a tool_loop suite: `{**full_suite(root), "delegate":
    make_delegate(responder=..., root=...)}`. Calling `delegate(task)` runs a child agent on `task` to a
    FinalAnswer at its own record root and returns `{answer, child_root, steps}`. `child_factory` overrides
    what the child is (default: a tool_loop over the full suite, nesting a deeper delegate up to
    `max_depth`); pass a deterministic scripted factory for reproducible CI. Depth and fan-out are capped —
    at either cap the call raises, which the loop turns into a typed ToolResult(ok=False)."""
    r = Path(root)
    factory = child_factory or _default_child_factory(
        responder, walkthrough, depth, max_depth, max_children, child_max_steps, timeout_seconds
    )
    spawned = {"n": 0}  # per-instance fan-out counter (the factory is built once per run)

    def run(a: list[Any]) -> dict[str, Any]:
        task = str(a[0]) if a else ""
        if depth >= max_depth:
            # the chain is at its limit — refuse, as a typed failure the model reads (never recurse past it)
            raise ValueError(f"delegate: max delegation depth ({max_depth}) reached — solve it directly")
        if spawned["n"] >= max_children:
            raise ValueError(f"delegate: max children ({max_children}) already spawned by this agent")
        spawned["n"] += 1
        child_root = r / "delegate-runs" / f"d{depth + 1}-c{spawned['n']}"
        topology = factory(task, child_root)
        answer, steps = _run_child_to_answer(topology, child_root, timeout_seconds=timeout_seconds)
        return {"answer": answer, "child_root": str(child_root), "steps": steps}

    return Tool(
        "delegate",
        "delegate(task) -> {answer, child_root, steps}: hand a self-contained subtask to a child agent; "
        "it runs to an answer as its own record and the answer folds back (SIDE EFFECT)",
        False,  # runs a real child agent — not deterministic in the pure sense
        run,
    )
