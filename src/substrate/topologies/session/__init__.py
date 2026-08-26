"""Session topology — the daily-driver tool_loop with pause_await_input on FinalAnswer.

The session lives for the length of a driver conversation. A UserMessage opens a turn;
the `model` producer reads the transcript and yields a ToolCall (dispatch a tool), a
ModelReply (visible text), or a FinalAnswer (turn done). Tools run through the same
seam as `tool_loop`. A FinalAnswer fires the `park` producer, which emits one Park and
completes; the topology's termination pauses the run awaiting the next UserMessage.
Slash commands and daemon-injected SessionEndRequested route through the `session_end`
producer to a SessionEnded and terminate the run.

Sprint 205 registered the four Producers, three Views, and eight Structs. Sprint 206
adds the ten triggers, composes termination as
`any_of(pause_await_input(on Park, resume_condition="UserMessage"), threshold_count("SessionEnded", 1))`,
and refuses `all_completed` at build time — a pausable topology on `all_completed`
hangs on resume because the paused Producer's ProducerStarted has no durable end
(policies.py:90-97). Producer bodies stay scaffolded; sprint 207 replaces them with
the real model / tool / park / session_end loop and the rolling-window transcript.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from typing import Any

from msgspec import Struct

import re

from ... import api
from ...adapters import DeterministicResponder, Responder
from ...kernel.policies import TerminationPolicy
from ..tool_loop import _tool_factory as _tool_loop_tool_factory
from ..tool_loop.tools import Tool

_ALL_COMPLETED_RE = re.compile(r"\ball_completed\b")


def _refuse_all_completed(policy: TerminationPolicy) -> None:
    """Reject `all_completed` at any nesting depth in the composed termination.

    Every built-in composer (`any_of`, `all_of`) concatenates its members' `.name`
    fields, so the leaf name `all_completed` from `policies.py:90` reappears verbatim
    inside the composed name. A word-boundary regex match catches direct use and every
    depth of composition (`any_of(all_completed(),...)`, `any_of(any_of(all_completed(),...),...)`,
    etc.) without paying the cost of walking closed-over sub-policies (they are not
    exposed as attributes). See `policies.py:90-97` for why a pausable topology on
    `all_completed` hangs on resume.
    """
    if _ALL_COMPLETED_RE.search(policy.name):
        raise api.RegistrationError(
            "session_topology termination policy contains `all_completed` "
            f"(name={policy.name!r}). A pausable topology on all_completed hangs on "
            "resume — the paused Producer's ProducerStarted has no durable end, so "
            "started > ended forever. See kernel/policies.py:90-97. Compose with "
            "quiescence_with_watchdog or threshold_count instead."
        )


# Event Structs — vocabulary lock at `substrate/process/signals/session-vocabulary.md`
# v0.1 (sprint 202, RATIFIED 2026-08-25). Eight PascalCase Structs, all frozen. Every
# name is application-scoped; none uses the reserved `substrate.` prefix.


class SessionStarted(Struct, frozen=True):
    session_id: str
    seed: str
    driver_model: str
    driver_context_tokens: int
    tool_suite: tuple[str, ...]
    workspace_path: str
    workspace_shape: str
    bundle: str | None
    baseline: dict[str, Any]
    parent_session_id: str | None
    parent_seq_at_call: int | None


class UserMessage(Struct, frozen=True):
    text: str
    turn_index: int
    assembled_prompt: str
    slash_source: str | None


class ModelReply(Struct, frozen=True):
    text: str
    model_usage: dict[str, Any]
    turn_index: int


class Park(Struct, frozen=True):
    awaiting: str
    turn_index: int
    reason: str


class SessionEnded(Struct, frozen=True):
    reason: str
    total_turns: int


class SessionEndRequested(Struct, frozen=True):
    session_id: str
    source: str


class SessionWarning(Struct, frozen=True):
    session_id: str
    kind: str
    seed_tokens: int
    driver_context_tokens: int


# Sprint 209a wires the four core producer bodies. The model producer reads the
# just-appended UserMessage / ToolResult and yields ToolCall / ModelReply / FinalAnswer.
# The tool producer is verbatim from `tool_loop` — same tool seam, same error-as-observation
# discipline. Park and session_end each yield one Struct and complete; both declared
# `deterministic=True` because the emission depends only on the trigger input.


_MAX_CONSECUTIVE_FAILS = 3


def _park_factory() -> Callable[[], Any]:
    async def _park(inp: Any) -> AsyncIterator[Park]:
        turn_index = int(inp.get("turn_index", 0)) if hasattr(inp, "get") else 0
        reason = str(inp.get("reason", "final_answer")) if hasattr(inp, "get") else "final_answer"
        yield Park(awaiting="UserMessage", turn_index=turn_index, reason=reason)

    return lambda: _park


def _session_end_factory() -> Callable[[], Any]:
    async def _session_end(inp: Any) -> AsyncIterator[SessionEnded]:
        reason = str(inp.get("reason", "user_exit")) if hasattr(inp, "get") else "user_exit"
        total_turns = int(inp.get("total_turns", 0)) if hasattr(inp, "get") else 0
        yield SessionEnded(reason=reason, total_turns=total_turns)

    return lambda: _session_end


def _model_factory(
    *,
    driver: Responder,
    per_turn: str,
    script: list[tuple[str, list[Any]]] | None,
) -> Callable[[], Any]:
    """Model Producer body. Yields ToolCall, ModelReply, or FinalAnswer per firing.

    Three dispatch paths in order:
      1. `final=True` on the wrap-up trigger's input: force a FinalAnswer synthesized
         from the last tool result (or a stubbed no-result note).
      2. `script` given: read `script[step]` as `(tool, args)` and yield a ToolCall;
         once the script exhausts, yield a FinalAnswer citing the last tool output.
         This is the CI dispatch path — a scripted deterministic driver keeps records
         byte-stable. It parallels `tool_loop`'s script hook.
      3. Otherwise: call `driver.respond(...)` on the assembled prompt (built from
         the seed-derived rolling transcript in a later sprint; for now the caller
         hands `assembled_prompt` on `resume-on-user` or a synthesized "continue"
         prompt on `continue`). Emit one `ModelReply` with the response text; if
         the response looks like a `TOOL: <name> args=[...]` line, yield a ToolCall
         instead. This is the minimal driver-parse path; sprint-210's observation
         contract runs against a real LLM via the same path.

    A run of `_MAX_CONSECUTIVE_FAILS` tool failures at the tail bails with a
    truthful FinalAnswer citing the last error — matches `tool_loop`'s anti-spin
    guard.
    """

    async def _model(inp: Any) -> AsyncIterator[ToolCall | ModelReply | FinalAnswer]:
        step = int(inp.get("step", 0)) if hasattr(inp, "get") else 0
        results = list(inp.get("results", [])) if hasattr(inp, "get") else []
        final = bool(inp.get("final", False)) if hasattr(inp, "get") else False
        turn_index = int(inp.get("turn_index", 0)) if hasattr(inp, "get") else 0
        assembled_prompt = str(inp.get("assembled_prompt", "")) if hasattr(inp, "get") else ""
        if final:
            text = _answer_text_from_results(results)
            yield FinalAnswer(text=text, steps=step)
            return
        trailing_fails = 0
        for r in reversed(results):
            if r.get("ok", True):
                break
            trailing_fails += 1
        if trailing_fails >= _MAX_CONSECUTIVE_FAILS:
            last_err = str(results[-1].get("error", "tool failed"))
            yield FinalAnswer(
                text=f"stopped after {trailing_fails} failed tool call(s): {last_err}",
                steps=step,
            )
            return
        if script is not None:
            if step < len(script):
                tool, args = script[step]
                yield ToolCall(call_id=f"c{step}", tool=tool, args=list(args), step=step)
            else:
                yield FinalAnswer(text=_answer_text_from_results(results), steps=step)
            return
        prompt = _prompt_for_driver(assembled_prompt, per_turn, results)
        reply_text = str(driver.respond(prompt))
        yield ModelReply(text=reply_text, model_usage={}, turn_index=turn_index)
        yield FinalAnswer(text=reply_text, steps=step)

    return lambda: _model


def _answer_text_from_results(results: list[dict[str, Any]]) -> str:
    if not results:
        return "no result"
    last = results[-1]
    if not last.get("ok", True):
        return f"stopped: {last.get('error', 'tool failed')}"
    return str(last.get("output", ""))


def _prompt_for_driver(
    assembled_prompt: str,
    per_turn: str,
    results: list[dict[str, Any]],
) -> str:
    lines: list[str] = []
    if per_turn:
        lines.append(per_turn.rstrip())
    if assembled_prompt:
        lines.append(assembled_prompt)
    if results:
        progress = [
            {"tool": r.get("tool"), "ok": r.get("ok", True), "output": r.get("output", "")}
            for r in results
        ]
        lines.append(f"Tool results so far: {progress}")
    return "\n".join(lines)


def _session_warning_factory(
    *,
    session_id: str,
    kind: str,
    seed_tokens: int,
    driver_context_tokens: int,
) -> Callable[[], Any]:
    """Producer for the seed-alone-exceeds SessionWarning (sprint 208).

    Emits exactly one `SessionWarning` and completes. The topology registers this
    factory under an `initial` only when the seed + per_turn cost exceeds the
    headroom threshold at session open; the producer therefore never fires more
    than once per session, satisfying the §F #6 cadence invariant structurally.
    """

    async def _emit(inp: Any) -> AsyncIterator[SessionWarning]:
        del inp
        yield SessionWarning(
            session_id=session_id,
            kind=kind,
            seed_tokens=seed_tokens,
            driver_context_tokens=driver_context_tokens,
        )

    return lambda: _emit


def session_topology(
    *,
    driver: Responder,
    driver_name: str,
    driver_context_tokens: int,
    seed: str,
    tools: dict[str, Tool],
    per_turn: str = "",
    max_turns: int = 200,
    turn_max_steps: int = 24,
    session_id: str,
    workspace_path: str,
    parent_session_id: str | None = None,
    parent_seq_at_call: int | None = None,
    script: list[tuple[str, list[Any]]] | None = None,
) -> Callable[[api.TopologyBuilder], None]:
    """Build the session topology.

    Thirteen keyword arguments name every input the daily-driver session opens with; the
    seed is the assembled string from §1.6.5 (composed by the daemon before this call).
    Sprint 205 registered Producers + Views + Structs. Sprint 206 added the ten triggers
    and composed termination. Sprint 208 added the `session_warning` producer + guard.
    Sprint 209a wires the four core producer bodies (model / tool / park / session_end).
    The `script` kwarg is the CI dispatch hook: a list of `(tool_name, args)` the model
    fires in order, matching `tool_loop`'s script convention; omit for the driver-parse
    path.
    """

    # `driver_name`, `workspace_path`, `parent_session_id`, `parent_seq_at_call` are
    # placeholders on the daemon's call-site contract; sprint 213/217/225 bind them.
    # They ride the signature so the outer daemon does not shift when they wire up.

    def _step_of(ctx: Any) -> int:
        payload = getattr(ctx.event, "payload", None) or {}
        return int(payload.get("step", turn_max_steps))

    def _turn_index(ctx: Any) -> int:
        # UserMessage KindCount rides `user_turns`; the count is 1-based right after
        # the just-appended UserMessage lands, so the current turn is count-1.
        n = int(ctx.views["user_turns"].value())
        return max(n - 1, 0)

    def _producer_kind_from_ref(ctx: Any) -> str | None:
        payload = getattr(ctx.event, "payload", None) or {}
        ref = payload.get("producer") if isinstance(payload, dict) else None
        return ref.get("kind") if isinstance(ref, dict) else None

    def _continue_input(ctx: Any, *, final: bool) -> dict[str, Any]:
        return {
            "step": _step_of(ctx) + 1,
            "results": list(ctx.views["results"].value()),
            "final": final,
            "turn_index": _turn_index(ctx),
        }

    # A scripted CI dispatch produces a byte-stable record; a real driver never does,
    # so the model producer stays `deterministic=False` in the driver-parse path.
    model_is_deterministic = script is not None and isinstance(driver, DeterministicResponder)

    def topo(b: api.TopologyBuilder) -> None:
        b.producer_kind(
            "model",
            schemas=[ToolCall, FinalAnswer, ModelReply, TranscriptCompacted],
            schema_version=1,
            factory=_model_factory(driver=driver, per_turn=per_turn, script=script),
            deterministic=model_is_deterministic,
        )
        b.producer_kind(
            "tool",
            schemas=[ToolResult],
            schema_version=1,
            factory=_tool_loop_tool_factory(tools),
            deterministic=all(t.deterministic for t in tools.values()) if tools else True,
        )
        b.producer_kind(
            "park",
            schemas=[Park],
            schema_version=1,
            factory=_park_factory(),
            deterministic=True,
        )
        b.producer_kind(
            "session_end",
            schemas=[SessionEnded],
            schema_version=1,
            factory=_session_end_factory(),
            deterministic=True,
        )
        # Seed-alone-exceeds guard per TECH-SPEC §3a. The threshold is the same
        # 60% headroom the transcript renderer uses (`driver_headroom_frac`), so a
        # session whose seed alone eats past that mark starts with zero room for
        # any turn to fit. Registration happens unconditionally; the `initial`
        # binding fires only when the check trips, which enforces the "at most
        # once per (session_id, condition_kind)" cadence structurally (the
        # producer emits once and completes; no trigger re-fires it).
        seed_tokens = _est_tokens(seed) + _est_tokens(per_turn)
        seed_alone_exceeds = seed_tokens > int(driver_context_tokens * 0.6)
        b.producer_kind(
            "session_warning",
            schemas=[SessionWarning],
            schema_version=1,
            factory=_session_warning_factory(
                session_id=session_id,
                kind="seed_alone_exceeds",
                seed_tokens=seed_tokens,
                driver_context_tokens=driver_context_tokens,
            ),
            deterministic=True,
        )
        if seed_alone_exceeds:
            b.initial("session_warning", input={})
        b.view("results", api.KindBuffer("ToolResult"))
        b.view("user_turns", api.KindCount("UserMessage"))
        b.view("model_failures", ModelFailures())

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
        b.trigger(
            "continue",
            subscription=api.Subscription(kinds=frozenset({"ToolResult"})),
            predicate=lambda ctx: _step_of(ctx) + 1 < turn_max_steps,
            starts="model",
            input_builder=lambda ctx: _continue_input(ctx, final=False),
            policy=api.PerEvent(),
        )
        b.trigger(
            "wrap-up",
            subscription=api.Subscription(kinds=frozenset({"ToolResult"})),
            predicate=lambda ctx: _step_of(ctx) + 1 >= turn_max_steps,
            starts="model",
            input_builder=lambda ctx: _continue_input(ctx, final=True),
            policy=api.PerEvent(),
        )
        b.trigger(
            "park-on-final",
            subscription=api.Subscription(kinds=frozenset({"FinalAnswer"})),
            predicate=lambda ctx: True,
            starts="park",
            input_builder=lambda ctx: {
                "turn_index": _turn_index(ctx),
                "reason": "final_answer",
            },
            policy=api.PerEvent(),
        )
        b.trigger(
            "park-on-model-error",
            subscription=api.Subscription(kinds=frozenset({"substrate.ProducerFailed"})),
            predicate=lambda ctx: _producer_kind_from_ref(ctx) == "model",
            starts="park",
            input_builder=lambda ctx: {
                "turn_index": _turn_index(ctx),
                "reason": "model_error",
            },
            policy=api.PerEvent(),
        )
        b.trigger(
            "park-on-interrupt",
            subscription=api.Subscription(kinds=frozenset({"substrate.ProducerCancelled"})),
            predicate=lambda ctx: _producer_kind_from_ref(ctx) == "model",
            starts="park",
            input_builder=lambda ctx: {
                "turn_index": _turn_index(ctx),
                "reason": "interrupt",
            },
            policy=api.PerEvent(),
        )
        b.trigger(
            "resume-on-user",
            subscription=api.Subscription(kinds=frozenset({"UserMessage"})),
            predicate=lambda ctx: True,
            starts="model",
            input_builder=lambda ctx: {
                "step": 0,
                "results": [],
                "final": False,
                "turn_index": _turn_index(ctx),
                "assembled_prompt": ctx.event.payload.get("assembled_prompt", ""),
            },
            policy=api.PerEvent(),
        )
        b.trigger(
            "end-on-exit",
            subscription=api.Subscription(kinds=frozenset({"UserMessage"})),
            predicate=lambda ctx: str(ctx.event.payload.get("text", "")).strip() == "/exit",
            starts="session_end",
            input_builder=lambda ctx: {
                "reason": "user_exit",
                "total_turns": _turn_index(ctx) + 1,
            },
            policy=api.Once(),
        )
        b.trigger(
            "end-on-cap",
            subscription=api.Subscription(kinds=frozenset({"UserMessage"})),
            predicate=lambda ctx: int(ctx.views["user_turns"].value()) >= max_turns,
            starts="session_end",
            input_builder=lambda ctx: {
                "reason": "timeout",
                "total_turns": int(ctx.views["user_turns"].value()),
            },
            policy=api.Once(),
        )
        b.trigger(
            "end-on-user-end",
            subscription=api.Subscription(kinds=frozenset({"SessionEndRequested"})),
            predicate=lambda ctx: True,
            starts="session_end",
            input_builder=lambda ctx: {
                "reason": "user_end",
                "total_turns": int(ctx.views["user_turns"].value()),
            },
            policy=api.Once(),
        )
        termination = api.any_of(
            api.pause_await_input(
                when=lambda tctx: tctx.event is not None and tctx.event.kind == "Park",
                resume_condition="UserMessage",
            ),
            api.threshold_count("SessionEnded", 1),
        )
        _refuse_all_completed(termination)
        b.termination(termination)

    return topo


# `SessionStarted`, `UserMessage`, `SessionEndRequested`, and `SessionWarning` do not
# appear in any `producer_kind(schemas=[...])` above because they arrive on the record
# from a different path: `SessionStarted` fires via an instrument on `substrate.RunStarted`
# (sprint 209 wires it), `UserMessage` and `SessionEndRequested` are external events
# injected by the daemon through `Runtime.resume(resume_event=...)`, and `SessionWarning`
# rides a `session_warning` producer added in sprint 208. Declaring them here keeps
# the eight-Struct vocabulary complete at the topology's Python surface.

# ToolCall / ToolResult / FinalAnswer are borrowed from `tool_loop` so the session
# reuses tool_loop's tool seam verbatim (product spec §4). The imports live below the
# session Structs so the file reads top-down: session's own vocabulary first, then
# the tool_loop borrow. tool_loop's schemas are already frozen msgspec Structs.
from ..tool_loop import FinalAnswer, ToolCall, ToolResult  # noqa: E402
from .transcript import (  # noqa: E402
    RenderedTranscript,
    TranscriptCompacted,
    _est_tokens,
    render_transcript,
    resolve_driver_context_tokens,
)
from .views import ModelFailures  # noqa: E402

__all__ = [
    "FinalAnswer",
    "ModelFailures",
    "ModelReply",
    "Park",
    "RenderedTranscript",
    "SessionEnded",
    "SessionEndRequested",
    "SessionStarted",
    "SessionWarning",
    "ToolCall",
    "ToolResult",
    "TranscriptCompacted",
    "UserMessage",
    "render_transcript",
    "resolve_driver_context_tokens",
    "session_topology",
]
