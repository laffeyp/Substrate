# The tool-using loop, and where it goes

The `tool_loop` topology (`src/substrate/topologies/tool_loop/`) is the classic agent loop —
a model that calls tools, reads results, and calls again until it answers — expressed as a
Substrate topology. It ships, with a committed CI record (`substrate demo replay tool_loop`).

The reason it is worth writing down where it goes: in Substrate the loop, the history, the
error handling, and the replay are the runtime's job, not the topology's. A hand-written agent
spends most of its code on that plumbing. Here it is gone, so the interesting work is
*composition* — and each direction below is a small delta on the shipped topology, expressed in
primitives that already exist. This document sketches those directions and names the mechanism
for each. It marks what ships today versus what is a sketch; nothing here is hidden behind a
"coming soon".

For the shape the loop already has — `ToolCall` → `tool` Producer → `ToolResult` re-fires the
`model`, bounded by a step budget that always ends on a `FinalAnswer`, with failed tools
surfacing as typed `ToolResult(ok=False, error=...)` observations rather than crashes — read the
module docstring. The patterns below build on that.

---

## 1. Parallel tool calls

**Status: sketch. Mechanism: a fan-out Trigger + a count predicate.**

Modern tool use lets a model request several tool calls at once when they are independent — read
three files, run two searches — and gather all the results before continuing. A sequential agent
runs them one at a time; this is the case Substrate is built for.

A model turn emits N `ToolCall` events instead of one. The existing `run-tool` Trigger is
`PerEvent`, so it already starts one `tool` Producer per call — N concurrent Producers, no
change. What changes is the *join*: instead of re-firing the model on each `ToolResult`, wait
until all N for this turn have landed, then fire once with the full batch.

```python
b.view("pending", api.KindCount("ToolCall"))     # calls issued this turn
b.view("done", api.KindCount("ToolResult"))      # results in this turn
b.trigger(
    "continue",
    subscription=api.Subscription(kinds=frozenset({"ToolResult"})),
    # fire the model once, when the last result of the turn lands
    predicate=lambda ctx: ctx.views["done"].value() == ctx.views["pending"].value(),
    starts="model",
    input_builder=lambda ctx: {"results": list(ctx.views["results"].value()), ...},
    policy=api.Once(),   # one continuation per completed batch
)
```

The win is real and measurable on the log: the `ProducerStarted` events for the N tools are
concurrent, and wall-clock for the turn is the slowest tool, not their sum. The same shape gives
you early-exit: a `cancel_all_others` decision on the first result that settles the question
cancels the siblings (this is exactly what `code_review` does when the judge fires).

---

## 2. Human-in-the-loop approval before irreversible tools

**Status: sketch. Mechanism: `pause_await_input` (the R-2 reference topology already does this).**

The standard guidance for agents that take real actions — delete data, send money, push code —
is a checkpoint: pause for human review before the irreversible step. In Substrate a pause is a
first-class run state on the log, not an out-of-band prompt.

Flag a tool as gated. When a `ToolCall` to a gated tool lands with no matching `Approval` yet,
the run pauses; an external `ApprovalGranted` event (supplied from outside the run,
`producer=null`) resumes it and the tool runs.

```python
b.termination(
    api.any_of(
        api.pause_await_input(
            lambda ctx: _has_gated_call_without_approval(ctx),
            resume_condition="ApprovalGranted",
        ),
        api.threshold_count("FinalAnswer", 1),
        api.quiescence_with_watchdog(seconds=60),
    )
)
```

This is the same mechanism R-2 uses to pause on `RetryExhausted` and resume on an operator
override — read `docs/walkthroughs/records/r2` to see a pause-and-resume on one continuous seq
sequence across a process boundary. The approval, the pause, and the resumed action are all on
the record: an auditable trail of who approved what, when, and what ran as a result.

---

## 3. Real tools, real models — and the determinism boundary

**Status: the seam ships; real tools are the author's to plug in.**

The shipped tools are pure functions so the CI record is byte-reproducible. Real tools do I/O —
HTTP, a shell, a database — and are not reproducible. The honest move is to mark the tool
Producer `deterministic=False`, exactly as `coding_flow` does for its real `ruff && mypy &&
pytest` gate. The run still produces a complete, replayable *record* (every call and result is on
the log); it just is not byte-identical re-execution. Truth about what the tool did is on the
record either way.

The `model` is the `Responder` seam, so it is model-agnostic. The same loop runs on a local
open-source model (`OllamaResponder`), or — via a `CliResponder` over a coding-agent CLI (Claude
Code, Codex, Gemini; see the CLI-backed-models research) — a *heterogeneous* agent whose model is
whichever provider you point each instantiation at. Different providers on the same loop, each
call replayable, is a research instrument as much as a product.

---

## 4. Sub-agents: a tool whose execution is another agent

**Status: sketch. Mechanism: embedded composition (R-3) or a recursive Trigger (recursive_decomposition).**

A tool does not have to be a leaf. A `delegate` tool can start a *sub-topology* — its own
tool-loop with its own model and tools — and return that sub-run's `FinalAnswer` as the
`ToolResult`. R-3 already runs an inner pipeline as an embedded substrate that exports only its
mapped result onto the outer run, with no inner kinds leaking across the boundary; a sub-agent is
that pattern with a tool-loop inside.

If instead the delegation is recursive — an agent that spawns agents that spawn agents — it is
`recursive_decomposition`'s one-recursive-Trigger property: the spawn tree falls out of a single
Trigger and a depth budget, with no per-depth wiring. Either way the sub-agent's full trace is on
a record, parented to the call that spawned it (`trace_ancestry` walks the lineage).

---

## 5. Durable, long-running agents

**Status: the runtime supports it; a long-running agent topology is unbuilt.**

On a persistent bus a run survives the process. An agent can run for a long time, pause awaiting
input or approval (§2), and resume later on the *same* seq sequence — its memory is the record,
not in-process state. This is the substrate's answer to "where does a long-running agent keep its
context": not a fragile in-memory transcript, but a durable, replayable log it reconstructs from.
`substrate resume` (and the UI's resume) reattach to a paused run and continue it.

---

## 6. The record is the evaluation trace

**Status: ships today, underused.**

Every tool call, every result (success and failure), every model decision, and every runtime
decision is a typed event on the log. That makes the record an evaluation artifact for free:

- Diff two agents (or two models behind the same loop) on the same task with `first_divergence` —
  the first seq where their decisions differ, by hash. This is the "how do different models
  respond to the same input" research, applied to agents.
- Replay a recorded run at Level 2 to verify every decision by hash; a regression shows up as a
  divergence, not a vibe.
- A confirmed-good run becomes a fixture: `assert_event` / `assert_sequence` over its trace turn
  a known-good agent session into a regression test (the test-from-capture pattern).

No separate eval harness is required; the thing that ran the agent already wrote the trace.

---

## 7. Error-recovery policies: compose the loop with the cascade

**Status: sketch. Mechanism: R-2's retry / escalate / pause patterns over `ToolResult(ok=False)`.**

Today a failed tool ends the loop with a reported failure. The richer behavior is R-2's
error-cascade applied to tool failures: a retry Trigger re-fires the tool with the failure reason
routed into its next input; escalate after N attempts to a different tool or a stronger model;
pause for a human (§2) when it cannot recover. These are not new primitives — they are R-2's
Triggers, Routes, and pause policy pointed at `ToolResult(ok=False)` instead of a transform fault.
Errors-as-observations (already shipped) is the precondition; the policy is the composition.

---

## What this adds up to

None of the above is a new kernel feature. Parallel calls are a count predicate; approval is a
pause policy; sub-agents are composition or recursion; durability is the persistent bus;
evaluation is the record read back; recovery is the error cascade. The tool-loop is small because
the runtime is doing the hard part — so "where it goes" is mostly a question of which existing
primitives you compose, and the record tells you honestly what the composition actually did.
