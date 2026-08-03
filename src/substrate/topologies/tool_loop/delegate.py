"""delegate — a tool that hands a subtask to a CHILD agent and folds the answer back (application-parity W2.1).

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

THE CHILD RUNS THE REAL MODEL. The default child factory runs `tool_loop` in walkthrough mode with the
supplied `responder` and the delegated `task` — it does NOT run the deterministic calculator demo. (An
earlier version defaulted `walkthrough=False`, which made the child deterministic and discarded both the
model and the task, folding a canned "20" back for every delegation; review F-2. A responder — or an
explicit `child_factory` — is now required, and the task is asserted to reach the child model in the
contract test.) Inject a `child_factory` for a deterministic child in CI.

CAPS + FAILURE. Depth (`max_depth`) bounds the delegation CHAIN; fan-out (`max_children`) bounds how many
children one delegate spawns. At either cap the tool returns a typed failure the model reads. A child that
raises or produces no FinalAnswer is a typed `ToolResult(ok=False)`, not a crash. A child that runs past
`timeout_seconds` is ABANDONED, not cancelled: a Python thread cannot be killed, so the worker (a daemon)
keeps running to its own bounded termination while the parent records `ToolResult(ok=False)` naming the
child root. Its record finalises later at that root — the two records do not contradict, they are ordered.
The child's tools write ONLY under its `workspace/` subdir — its record is a SIBLING `record/` subdir, so
an autonomous child cannot write over the immutable evidence of its own run (C-1) — and it inherits the
parent's capability set via `child_suite_factory` (so `--read-only` survives delegation; review F-5). The real bound on a
child is its own `child_max_steps × the model call timeout`; set `timeout_seconds` above that — it is the
safety net, not the primary bound.
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

# What the child IS, given a subtask and its WORKSPACE root (where its tools operate — distinct from the
# record root, review C-1). Caller-supplied so delegate is agnostic to session-vs-named-topology, and CI
# can inject a deterministic child. Returns a topology builder callable.
ChildFactory = Callable[[str, Path], Callable[[api.TopologyBuilder], None]]
# How the child's tool suite is built at its own root — the seam through which the parent's capability set
# (e.g. read-only) propagates to the child instead of being silently rebuilt as the full suite.
SuiteFactory = Callable[[Path], dict[str, Tool]]


def _run_child_to_answer(
    topology: Callable[[api.TopologyBuilder], None],
    root: Path,
    *,
    timeout_seconds: float,
) -> tuple[str, int]:
    """Run `topology` to completion at `root` in a worker thread (its own event loop, isolated from the
    outer runtime's), then read the child's FinalAnswer off its record. Blocks the caller like `bash`.
    Raises TimeoutError (child abandoned, still running at `root`) / the child's exception / ValueError
    (no FinalAnswer) — the tool body turns any of these into a typed ToolResult the parent reads."""
    box: dict[str, Any] = {}

    def worker() -> None:
        try:
            box["result"] = asyncio.run(api.Runtime(root).run(topology))
        except BaseException as exc:  # carried back to the caller thread, not swallowed
            box["error"] = exc

    # daemon: a hung child never blocks process exit. It cannot be killed, so on timeout it is abandoned
    # to its own bounded termination — the error below names the root so the later-finalising child record
    # is legible, not a silent contradiction.
    t = threading.Thread(target=worker, daemon=True)
    t.start()
    t.join(timeout=timeout_seconds)
    if t.is_alive():
        raise TimeoutError(
            f"delegate child at {root} exceeded {timeout_seconds}s and was abandoned; it may still be "
            "running and finalise its own record later"
        )
    if "error" in box:
        raise box["error"]
    events = list(api.read_record(root))
    answer = next((e for e in events if e["kind"] == "FinalAnswer"), None)
    if answer is None:
        raise ValueError(f"delegate child at {root} produced no FinalAnswer")
    payload = answer["payload"]
    return str(payload.get("text", "")), int(payload.get("steps", 0))


def _default_child_factory(
    responder: Responder,
    suite_factory: SuiteFactory,
    depth: int,
    max_depth: int,
    max_children: int,
    child_max_steps: int,
    timeout_seconds: float,
) -> ChildFactory:
    """The child is a real tool_loop agent (walkthrough mode — it runs `responder` on the delegated task)
    over `suite_factory(workspace_root)`, plus a DEEPER delegate (depth+1) when the chain has room — so a
    delegated agent can itself delegate, bounded by max_depth, inheriting the same suite factory. A nested
    delegate roots at the DELEGATION dir (`workspace_root.parent`), not the workspace, so a grandchild's
    record is a sibling of this child's workspace — never underneath it (review C-1)."""
    from . import tool_loop_topology

    def factory(task: str, workspace_root: Path) -> Callable[[api.TopologyBuilder], None]:
        suite = suite_factory(workspace_root)
        if depth + 1 < max_depth:
            suite = {
                **suite,
                "delegate": make_delegate(
                    responder=responder,
                    root=workspace_root.parent,
                    child_suite_factory=suite_factory,
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
            walkthrough=True,  # run the REAL model on the REAL task (F-2), never the scripted demo
            max_steps=child_max_steps,
            deterministic=False,
        )

    return factory


def _unique_child_root(base: Path, depth: int, start: int) -> tuple[Path, int]:
    """A delegation dir (holding the child's `workspace/` + `record/`) that does not already exist on
    disk. Probing disk (not just an in-memory counter) is what prevents a FRESH delegate instance in a
    persistent workspace from reusing `d1-c1` and appending onto a sealed record — the RecordGapError
    data-loss path (review F-3)."""
    n = start
    child_root = base / f"d{depth + 1}-c{n}"
    while child_root.exists():
        n += 1
        child_root = base / f"d{depth + 1}-c{n}"
    return child_root, n


def make_delegate(
    *,
    child_factory: ChildFactory | None = None,
    responder: Responder | None = None,
    root: Path | str = ".",
    child_suite_factory: SuiteFactory | None = None,
    depth: int = 0,
    max_depth: int = 2,
    max_children: int = 4,
    child_max_steps: int = 6,
    timeout_seconds: float = 600.0,
) -> Tool:
    """A `delegate` Tool the caller composes into a tool_loop suite: `{**full_suite(root), "delegate":
    make_delegate(responder=..., root=...)}`. Calling `delegate(task)` runs a child agent on `task` to a
    FinalAnswer at its own record root and returns `{answer, child_root, steps}`.

    The child runs the REAL model on the REAL task. Supply either `responder` (the default factory runs a
    tool_loop agent with it) or `child_factory` (what the child is — a session, a named topology, or a
    deterministic scripted agent for CI); one is required. `child_suite_factory(workspace_root) -> suite`
    builds the child's tools (default `full_suite`) — pass the parent's own suite builder so a restricted
    parent (e.g. read-only) yields a restricted child. The child's tools operate in a `workspace/` subdir
    of the delegation dir; its record lives in a sibling `record/` subdir, so the child cannot write over
    its own record (C-1). Depth and fan-out are capped; at either cap the call raises, which the loop
    turns into a typed ToolResult(ok=False)."""
    r = Path(root)
    if child_factory is None and responder is None:
        raise ValueError("make_delegate requires either a responder or a child_factory")
    suite_factory: SuiteFactory = child_suite_factory or full_suite
    if child_factory is not None:
        factory: ChildFactory = child_factory
    else:
        assert responder is not None  # guarded above; narrows for the type checker
        factory = _default_child_factory(
            responder,
            suite_factory,
            depth,
            max_depth,
            max_children,
            child_max_steps,
            timeout_seconds,
        )
    spawned = {"n": 0}  # per-instance fan-out counter (the factory is built once per run)

    def run(a: list[Any]) -> dict[str, Any]:
        task = str(a[0]) if a else ""
        if depth >= max_depth:
            # the chain is at its limit — refuse, as a typed failure the model reads (never recurse past it)
            raise ValueError(
                f"delegate: max delegation depth ({max_depth}) reached — solve it directly"
            )
        if spawned["n"] >= max_children:
            raise ValueError(
                f"delegate: max children ({max_children}) already spawned by this agent"
            )
        # a delegation dir that does not already exist (F-3): reuse would append onto a sealed record
        # and lose data. Inside it, WORKSPACE and RECORD are SEPARATE subdirs (review C-1): the child's
        # bash/write_file/edit_file are rooted at `workspace/`, the append-only record lives at `record/`,
        # so an autonomous child cannot write over the immutable evidence of its own run. The two are
        # opposite kinds of thing; one path can't stand for both.
        delegation_dir, n = _unique_child_root(r / "delegate-runs", depth, spawned["n"])
        spawned["n"] = n + 1
        workspace_root = delegation_dir / "workspace"
        record_root = delegation_dir / "record"
        topology = factory(
            task, workspace_root
        )  # the child's tools operate in workspace, NOT the record
        answer, steps = _run_child_to_answer(topology, record_root, timeout_seconds=timeout_seconds)
        return {"answer": answer, "child_root": str(record_root), "steps": steps}

    return Tool(
        "delegate",
        "delegate(task) -> {answer, child_root, steps}: hand a self-contained subtask to a child agent; "
        "it runs to an answer as its own record and the answer folds back (SIDE EFFECT)",
        False,  # runs a real child agent — not deterministic in the pure sense
        run,
        # the schema travels WITH the tool (review C-10), not as a row in tools.py's closed literal — so
        # delegate is visible to native tool-calling without tools.py needing to know delegate exists.
        {"type": "object", "properties": {"task": {"type": "string"}}, "required": ["task"]},
    )
