# Sprint 141 — delegate: an agent mid-run starts a child and folds the result back

---

```yaml
---
id: 141
status: closed
phase: 2
pass_kind: functional
cadence_band: plan-mode-per-sprint
---
```

---

## why

Phase W2.1, the first ENGINE SEAM of the workflow-parity work (`docs/cockpit/WORKFLOW-PARITY-SPRINTS-2026-07-31.md`). W1 was compose-only. `delegate` is a tool a tool-using agent can call mid-run to hand a sub-task to a CHILD agent, run it to completion, and fold its answer back into the parent's transcript — the "subagent" the CLI products ship, on substrate, where the child is a full replayable record cited from the parent's.

## the seam (read before building)

`tool_loop`'s `Tool.run` is SYNCHRONOUS (`tools.py:58`, called un-awaited at `__init__.py:304`) — a tool blocks the outer loop while it runs (`bash` already does, `subprocess.run(timeout=60)`). A child substrate run is async. So `delegate` runs the child to completion in a WORKER THREAD hosting its own `asyncio.run`, and blocks on it exactly as `bash` blocks — no new async contract in the tool seam. This is the "launch path (peer session)" the plan names, not the Producer-export path: `embedded_substrate` is a Producer, and the tool seam cannot mount a Producer. Provenance is RUN-granularity (the child's record root, returned in the ToolResult, is recorded in the parent record) — the same guarantee `embedded_substrate` gives (composition.py:24-31), reached through the tool result instead of the export map.

## scope

Author `delegate` as a `Tool` factory (`make_delegate`) the caller composes into a suite, exactly as `FULL_SUITE` is passed into `tool_loop_topology(tools=...)`. It does NOT go into `tools.py`'s `full_suite` (which stays free of model/topology dependencies); it lives in its own module and is added by the caller: `{**full_suite(root), "delegate": make_delegate(...)}`. What the child IS is caller-supplied via a `child_factory(task, child_root) -> topology` (a tool_loop, a named topology, a scripted deterministic agent for CI) — so delegate is agnostic to session-vs-topology, and CI stays deterministic. Depth and fan-out are capped.

## signal contract

### Emits

No new event kind. `delegate` is a tool; its result is an ordinary `ToolResult` (tool_loop's locked kind) whose `output` is `{answer, child_root, steps}`. The child run emits tool_loop's own kinds at the CHILD root.

### Invariants

- No new vocabulary; `tool_loop/__init__.py` and `tools.py` are not modified. **AMENDED (2026-07-31,
  review F-26): this invariant was BROKEN and the sprint closed on it anyway. `tools.py` WAS modified —
  to register `delegate`'s schema in `_TOOL_SCHEMAS`, without which the tool is invisible to native
  tool-calling (the walkthrough caught it). The "no engine change" framing was the premise this
  invariant expressed, and registering a schema for a new tool is a (small) engine change. The Built
  entry narrated the fix honestly; this card did not. Corrected: delegate touches `tools.py`'s schema
  registry by necessity — a tool absent there cannot be called by a real model.**
- The child runs at its OWN record root (a `delegate-runs/` subdir of the parent workspace); the parent's ToolResult carries `child_root` so the child record is citable (run-granularity provenance).
- Depth cap: a delegate at `depth >= max_depth` returns a typed failure, never spawns — no unbounded recursion.
- Fan-out cap: at most `max_children` spawns per delegate instance; the next returns a typed failure.
- A child that produces no `FinalAnswer`, raises, or exceeds a wall-clock timeout is a typed `ToolResult(ok=False)` the parent reads — never a crash, never a silent hang (the worker thread is a daemon so a timed-out child cannot wedge process exit).

## artifact contract

### Files created

- `src/substrate/topologies/tool_loop/delegate.py` — `make_delegate(*, child_factory=None, responder=None, root=".", walkthrough=False, depth=0, max_depth=2, max_children=4, child_max_steps=6, timeout_seconds=120.0) -> Tool` and `_run_child_to_answer(topology, root, *, timeout_seconds) -> tuple[str, int]`. The default `child_factory` builds a `tool_loop` with `full_suite(child_root)` plus a deeper `delegate` (depth+1) when `depth+1 < max_depth`. (One concept, ≤2 files.)
- `tests/test_delegate.py` — the observation contract.

### Files modified

- `process/WORKING_AGREEMENT.md` — canonical-home row for `make_delegate`.
- `scripts/run_tool_agent.py` — a `--delegate` flag that composes `make_delegate` into the suite (the real-model walkthrough surface). If it complicates the script, a separate `scripts/run_delegate.py` instead; do not bloat run_tool_agent.

### Content assertions

- `make_delegate(...)` returns a `Tool` named `delegate`; its `run([task])` runs a child to a `FinalAnswer` and returns `{"answer": str, "child_root": str, "steps": int}`.
- Depth at cap and fan-out at cap each raise (→ the loop turns it into `ToolResult(ok=False)`).
- The child record exists at the returned `child_root` and reaches `substrate.RunFinalised`.

### Command exit codes

- `uv run python -m pytest tests/test_delegate.py -q` returns 0
- `uv run ruff check src/substrate/topologies/tool_loop/delegate.py` returns 0
- `uv run mypy src/substrate/topologies/tool_loop/delegate.py` returns 0
- `PATH="$PWD/.venv/bin:$PATH" uv run python -m pytest -q` returns 0 (full suite)

## observation contract

`pass_kind: functional`. Behavior: a parent agent delegates a subtask; the child runs as its own record; the answer folds back.

### Input fixture (CI, deterministic)

- A parent `tool_loop` whose scripted model calls `delegate("compute (2+3)*4")` once, then answers with the delegated result. The `child_factory` builds a deterministic scripted calculator `tool_loop` (pure `CALCULATOR` suite) → the child answer is reproducible, no network. Both parent and child records are byte-stable.

### Expected runtime signals

- Parent: `ToolCall(delegate)` → `ToolResult(ok=True)` whose `output.child_root` names an existing record → `FinalAnswer`. Parent reaches `substrate.RunFinalised`.
- Child (at `child_root`): the calculator's `ToolCall`/`ToolResult` chain → `FinalAnswer` → `substrate.RunFinalised`.
- Cap tests: a delegate built at `depth=max_depth` yields `ToolResult(ok=False, error~="max depth")`; the `(max_children+1)`-th spawn yields `ok=False, error~="max children"`.

### Expected walkthrough (real model — named, human-run)

- `run_tool_agent.py --delegate --model <tag>` on a splittable task: the agent delegates a subtask, the child record shows a real sub-agent run, the answer folds back. Kept as the W2.1 walkthrough.

## done criteria

An agent calls `delegate`, a child agent runs as its own replayable record cited from the parent's ToolResult, and the answer folds back; depth and fan-out are capped with typed failures; a hung/failed child is a typed observation, not a crash; CI is deterministic (scripted parent + scripted child); full suite green. The tool_loop core is unmodified.

## notes

- W2.2 (sprint 142) puts the child on the record/flow in substrate-ui — a UI stitch across two records via `child_root`, NOT per-frame interleaving (the wire `ProducerRef` has no inner-provenance slot; composition.py:28). Build 142 on that understanding.
- The blocking-thread execution is consistent with `bash`'s blocking `subprocess.run`; a concurrent-Producer delegate (via `embedded_substrate`) is a separate, later shape if concurrency of the child with the parent's other work is ever wanted — out of scope here.
