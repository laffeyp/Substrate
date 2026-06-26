"""Tool-using loop topology — the classic model -> tool -> model agent loop (Wave 14).

A `model` Producer reads the task and the tool results so far and emits EITHER a `ToolCall`
(it wants a tool run) OR a `FinalAnswer` (it is done). A Trigger fires the named `tool`
Producer on each ToolCall; the `ToolResult` re-fires the model with that result appended —
the loop the whole "AI agent with tools" idea is built on, except the loop, the history, and
the replay are the runtime's job, not yours. Each model call and each tool call is its own
Producer instantiation, so every step is independently inspectable and replayable on the log.

Two properties this follows from real agent harnesses (opencode's `tool.ts` / `max-steps.ts`),
both of which fall out naturally in the substrate's typed-event model:

  - A failed tool is an OBSERVATION, not a crash. An unknown tool, a bad call, or a non-encodable
    result emits a typed `ToolResult` with `ok=False` and an `error` the model reads and reacts to —
    never an uncaught exception. (The substrate's own R-2 reference topology is the same discipline:
    a structured error on the log, then recovery.)
  - The step budget ends gracefully. At `max_steps` the loop fires the model once more with
    tools disabled (`final=True`) so the run ALWAYS ends on a `FinalAnswer`, never a silent
    quiescence stop — opencode's MAX_STEPS behavior.

CI: a deterministic scripted model — a tiny calculator agent computing (2 + 3) * 4 with `add`
and `mul` tools — pure and reproducible, so it ships a committed record. `walkthrough=True`
swaps in a real local LLM deciding via a one-line TOOL/ANSWER reply convention.

Extensions, both native to the substrate (not built here, but the shape is one Trigger away):
  - PARALLEL tool calls: a model turn emitting N ToolCalls starts N tool Producers concurrently;
    gather them with a count predicate (`KindCount`) before the continue fires — the substrate's
    concurrency is the point, where a sequential agent loop would run them one at a time.
  - HUMAN-IN-THE-LOOP: gate a side-effecting tool behind `pause_await_input` (the R-2 mechanism)
    so an irreversible action waits for approval before it runs.
  - SIDE-EFFECTING tools (real search / code-exec / HTTP) are non-deterministic: set the tool
    Producer `deterministic=False` (like `coding_flow`'s real gate). The run still produces a
    replayable record; it just is not byte-identical re-execution.

These are worked out as topology sketches in `docs/tool-loop-futures.md`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from typing import Any

from msgspec import Struct

from ... import api
from ...encoding import canonical_bytes
from ...reference._models import Responder, call_responder
from .tools import CALCULATOR, Tool, suite_describe

_Factory = Callable[[], Any]

# The tool registry lives in tools.py — PURE (the calculator) for the deterministic CI demo, plus
# the real READ-ONLY and WRITE/EXEC suite a real agent passes in. CALCULATOR is the default so the
# committed record stays byte-stable; a real run passes FULL_SUITE (deterministic=False). The suite
# design is grounded in the source of opencode / Cline / aider — see docs/tool-loop-tool-suite.md.


class ToolCall(Struct, frozen=True):
    call_id: str
    tool: str
    args: list[Any]  # ints for the calculator; strings (paths, patterns) for the real suite
    step: int


class ToolResult(Struct, frozen=True):
    call_id: str
    tool: str
    output: Any  # int / str / list / dict — whatever the tool returns (RFC-8785-encodable)
    step: int
    ok: bool = True
    error: str = ""


class FinalAnswer(Struct, frozen=True):
    text: str
    steps: int


def _answer_text(results: list[dict[str, Any]]) -> str:
    """The model's final text: the last successful output, or a note that there isn't one."""
    return str(results[-1]["output"]) if results and results[-1].get("ok", True) else "no result"


def _model_factory(
    responder: Responder | None,
    walkthrough: bool,
    script: list[tuple[str, list[Any]]] | None,
    tools: dict[str, Tool],
) -> _Factory:
    async def model(inp: Any) -> AsyncIterator[ToolCall | FinalAnswer]:
        step = int(inp.get("step", 0)) if hasattr(inp, "get") else 0
        results = list(inp.get("results", [])) if hasattr(inp, "get") else []
        final = bool(inp.get("final", False)) if hasattr(inp, "get") else False
        # budget wrap-up: tools are disabled, the model must answer (opencode MAX_STEPS pattern).
        if final:
            yield FinalAnswer(text=_answer_text(results), steps=step)
            return
        # a failed tool is an OBSERVATION: stop and report it (a stronger model could retry).
        if results and not results[-1].get("ok", True):
            yield FinalAnswer(
                text=f"stopped: {results[-1].get('error', 'tool failed')}", steps=step
            )
            return
        if walkthrough and responder is not None:
            # real model: ask for the next action; the reply convention is one line, either
            # "TOOL <name> <a> <b>" or "ANSWER <value>".
            outputs = [r["output"] for r in results]
            menu = suite_describe(tools)
            reply = await call_responder(
                responder,
                f"Tools:\n{menu}\nResults so far: {outputs}. Compute (2 + 3) * 4. "
                f"Reply with exactly one line: 'TOOL <name> <a> <b>' or 'ANSWER <value>'.",
            )
            head = reply.strip().splitlines()[0].split() if reply.strip() else ["ANSWER", ""]
            tool_call: ToolCall | None = None
            if head[0].upper() == "TOOL" and len(head) >= 4 and head[1] in tools:
                try:
                    tool_call = ToolCall(
                        call_id=f"c{step}",
                        tool=head[1],
                        args=[int(head[2]), int(head[3])],
                        step=step,
                    )
                except ValueError:
                    # a weak model (llama3.2:1b) emits non-integer args -> fall through to an answer,
                    # never crash the model Producer (which would wedge the loop).
                    tool_call = None
            if tool_call is not None:
                yield tool_call
            else:
                yield FinalAnswer(text=(head[-1] if len(head) > 1 else ""), steps=step)
            return
        # deterministic CI policy: a custom action script (a test hook, like recursive's `runaway`
        # or conversation's `converge_at`) or the default calculator agent.
        if script is not None:
            if step < len(script):
                tool, args = script[step]
                yield ToolCall(call_id=f"c{step}", tool=tool, args=list(args), step=step)
            else:
                yield FinalAnswer(text=_answer_text(results), steps=step)
            return
        # default calculator: (2 + 3) * 4 — calls `add`, then `mul` USING THE FIRST RESULT, then
        # answers, so it exercises the result-fed-back-in path, not a script blind to the tools.
        if step == 0:
            yield ToolCall(call_id="c0", tool="add", args=[2, 3], step=0)
        elif step == 1:
            yield ToolCall(call_id="c1", tool="mul", args=[results[-1]["output"], 4], step=1)
        else:
            yield FinalAnswer(text=str(results[-1]["output"]), steps=step)

    return lambda: model


def _tool_factory(tools: dict[str, Tool]) -> _Factory:
    async def run_tool(inp: Any) -> AsyncIterator[ToolResult]:
        tool = str(inp.get("tool")) if hasattr(inp, "get") else ""
        args = list(inp.get("args", [])) if hasattr(inp, "get") else []
        call_id = str(inp.get("call_id", "?")) if hasattr(inp, "get") else "?"
        step = int(inp.get("step", 0)) if hasattr(inp, "get") else 0
        entry = tools.get(tool)
        if entry is None:
            # unknown tool -> a typed failure the model reads, NOT a crash.
            yield ToolResult(
                call_id=call_id,
                tool=tool,
                output="",
                step=step,
                ok=False,
                error=f"unknown tool '{tool}'",
            )
            return
        try:
            output = entry.run(args)
            # pre-validate encodability so a non-RFC-8785-encodable return becomes a typed failure
            # HERE, not an emit-time crash (the yield's encode runs in the runtime, outside this try).
            canonical_bytes(output)
        except (
            Exception
        ) as exc:  # bad args / not-found / IO / non-encodable output -> ok=False, no crash
            yield ToolResult(
                call_id=call_id,
                tool=tool,
                output="",
                step=step,
                ok=False,
                error=f"{type(exc).__name__}: {exc}",
            )
            return
        yield ToolResult(call_id=call_id, tool=tool, output=output, step=step, ok=True)

    return lambda: run_tool


def tool_loop_topology(
    *,
    model: Responder | None = None,
    script: list[tuple[str, list[Any]]] | None = None,
    max_steps: int = 4,
    walkthrough: bool = False,
    deterministic: bool = True,
    tools: dict[str, Tool] | None = None,
) -> Callable[[api.TopologyBuilder], None]:
    """Build the tool-using loop. The `model` emits a ToolCall or a FinalAnswer; the named tool
    runs and its ToolResult re-fires the model with the result appended, until a FinalAnswer
    lands. The loop is bounded by `max_steps`: at the budget the model is fired once more with
    tools disabled so the run always ends on a FinalAnswer. A failed tool emits a typed
    ToolResult(ok=False) the model reacts to. CI uses a deterministic calculator agent (or a
    `script` of (tool, args) calls as a test hook); `walkthrough=True` swaps in a real local LLM."""

    from ...reference._models import OllamaResponder

    responder = (model or OllamaResponder("llama3.2:1b")) if walkthrough else model
    # default to the PURE calculator (the byte-reproducible CI demo); a real agent passes FULL_SUITE.
    # the run is deterministic only if every tool is pure AND it is NOT the walkthrough path: a real
    # model is not author-deterministic, so a walkthrough must never be stamped deterministic in the
    # manifest (CI runs walkthrough=False, so the committed calculator record is unaffected).
    suite = tools if tools is not None else CALCULATOR
    det = deterministic and not walkthrough and all(t.deterministic for t in suite.values())

    def _continue_input(ctx: Any, *, final: bool) -> dict[str, Any]:
        return {
            "step": int(ctx.event.payload["step"]) + 1,
            "results": list(ctx.views["results"].value()),
            "final": final,
        }

    def topo(b: api.TopologyBuilder) -> None:
        b.producer_kind(
            "model",
            schemas=[ToolCall, FinalAnswer],
            schema_version=1,
            factory=_model_factory(responder, walkthrough, script, suite),
            deterministic=det,
        )
        b.producer_kind(
            "tool",
            schemas=[ToolResult],
            schema_version=1,
            factory=_tool_factory(suite),
            deterministic=det,
        )
        b.initial("model", input={"step": 0, "results": [], "final": False})
        # the running transcript of tool results — the model reads it to decide the next step
        # (the full structured result is on the log; the model is handed exactly this).
        b.view("results", api.KindBuffer("ToolResult"))
        # each ToolCall runs its tool.
        b.trigger(
            "run-tool",
            subscription=api.Subscription(kinds=frozenset({"ToolCall"})),
            predicate=lambda ctx: True,
            starts="tool",
            input_builder=lambda ctx: {
                "call_id": ctx.event.payload["call_id"],
                "tool": ctx.event.payload["tool"],
                "args": list(ctx.event.payload["args"]),
                "step": int(ctx.event.payload["step"]),
            },
            policy=api.PerEvent(),
        )
        # within budget: each ToolResult re-fires the model with the result appended.
        b.trigger(
            "continue",
            subscription=api.Subscription(kinds=frozenset({"ToolResult"})),
            predicate=lambda ctx: int(ctx.event.payload["step"]) + 1 < max_steps,
            starts="model",
            input_builder=lambda ctx: _continue_input(ctx, final=False),
            policy=api.PerEvent(),
        )
        # at the budget: fire the model once more with tools disabled so the run ends on a
        # FinalAnswer rather than a silent quiescence stop (the bound is on the log).
        b.trigger(
            "wrap-up",
            subscription=api.Subscription(kinds=frozenset({"ToolResult"})),
            predicate=lambda ctx: int(ctx.event.payload["step"]) + 1 >= max_steps,
            starts="model",
            input_builder=lambda ctx: _continue_input(ctx, final=True),
            policy=api.PerEvent(),
        )
        # end the instant the model answers; quiescence backstops a wedged Producer.
        b.termination(
            api.any_of(
                api.threshold_count("FinalAnswer", 1),
                api.quiescence_with_watchdog(seconds=1),
            )
        )

    return topo
