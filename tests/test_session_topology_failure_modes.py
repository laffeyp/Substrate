"""Sprint 243 — session-topology failure-mode end-to-end tests.

Three trigger paths product spec §10 / tech spec §11 name but the existing
session-topology tests do not walk end-to-end:

- `park-on-model-error` — model producer raises → PRODUCER_FAILED → park →
  Park{reason:"model_error"} → run pauses → next UserMessage resumes.
- `park-on-interrupt` — model producer cancelled mid-turn → PRODUCER_CANCELLED →
  park → Park{reason:"interrupt"} → run pauses → next UserMessage resumes.
- `end-on-cap` — the (max_turns + 1)th UserMessage fires `end-on-cap` →
  SessionEnded{reason:"timeout", total_turns:max_turns} → RunFinalised.

Each test builds the session topology directly (no CI wrapper): `first_turn_user_message`
opens turn 1 on `Runtime.run()`; `Runtime.resume(topology, resume_event=UserMessage(...))`
drives subsequent turns. That mirrors the daemon path at
`substrate-ui/session_registry.py::turn_sync`.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from substrate import api
from substrate.topologies.session import (
    UserMessage,
    session_topology,
)
from substrate.topologies.tool_loop.tools import CALCULATOR

# ── shared test scaffolding ────────────────────────────────────────────


class _RaisingResponder:
    """Raises on every prompt. Drives park-on-model-error."""

    def respond(self, prompt: str) -> str:  # sync path (unused here)
        raise RuntimeError(f"induced model failure: prompt_len={len(prompt)}")

    async def arespond(self, prompt: str) -> str:
        raise RuntimeError(f"induced model failure: prompt_len={len(prompt)}")


class _SlowResponder:
    """Blocks for `delay` seconds on `arespond`. Drives park-on-interrupt —
    the interrupt-driver coroutine has a window to call cancel_producer while
    the model producer is running."""

    def __init__(self, delay: float = 10.0) -> None:
        self._delay = delay

    def respond(self, prompt: str) -> str:
        return f"slow[{prompt[:12]}]"

    async def arespond(self, prompt: str) -> str:
        await asyncio.sleep(self._delay)
        return f"slow[{prompt[:12]}]"


class _FastResponder:
    """One-shot final answer. Used to close a session cleanly after a resume."""

    def respond(self, prompt: str) -> str:
        return f"done[{prompt[:12]}]"

    async def arespond(self, prompt: str) -> str:
        return f"done[{prompt[:12]}]"


def _build(
    *,
    driver: Any,
    first_user_text: str,
    session_id: str,
    workspace: str,
    max_turns: int = 200,
) -> Callable[[api.TopologyBuilder], None]:
    """Build a session_topology configured to open with a scripted first turn."""
    return session_topology(
        driver=driver,
        driver_name="test",
        driver_context_tokens=4096,
        seed="failure-mode test",
        tools=CALCULATOR,
        per_turn="",
        max_turns=max_turns,
        turn_max_steps=8,
        session_id=session_id,
        workspace_path=workspace,
        script=None,
        first_turn_user_message=UserMessage(
            text=first_user_text,
            turn_index=0,
            assembled_prompt=first_user_text,
            slash_source="test",
        ),
    )


def _read(root: Path) -> list[dict[str, Any]]:
    return list(api.read_record(root))


def _by_kind(envelopes: list[dict[str, Any]], kind: str) -> list[dict[str, Any]]:
    return [e for e in envelopes if e["kind"] == kind]


def _park_reasons(envelopes: list[dict[str, Any]]) -> list[str]:
    return [str(e["payload"].get("reason", "")) for e in _by_kind(envelopes, "Park")]


# ── test 1: park-on-model-error ────────────────────────────────────────


@pytest.mark.asyncio
async def test_park_on_model_error_then_resume(tmp_path: Path) -> None:
    """A model producer that raises during turn 1 → PRODUCER_FAILED → park-on-model-error
    fires → Park{reason:"model_error"}. Then Runtime.resume with the next UserMessage +
    a working responder → the session resumes on the same record."""
    root = tmp_path / "park-on-model-error"

    # Turn 1: raising responder, expect Park{model_error}.
    fail_topology = _build(
        driver=_RaisingResponder(),
        first_user_text="please fail",
        session_id="s_fail",
        workspace=str(tmp_path / "ws"),
    )
    result_1 = await api.Runtime(root, persistent=True).run(fail_topology)
    assert result_1.status == "paused", f"turn 1 expected paused, got {result_1.status}"

    envelopes = _read(root)
    failures = _by_kind(envelopes, "substrate.ProducerFailed")
    assert failures, "expected at least one substrate.ProducerFailed after raising responder"
    # producer.kind == "model" for at least one failure.
    model_failures = [
        e for e in failures if (e["payload"].get("producer") or {}).get("kind") == "model"
    ]
    assert model_failures, (
        f"expected a model ProducerFailed, got kinds {[(e['payload'].get('producer') or {}).get('kind') for e in failures]}"
    )

    reasons = _park_reasons(envelopes)
    assert "model_error" in reasons, f"expected Park{{reason:model_error}}, got {reasons}"

    # Turn 2: working responder + Runtime.resume — the same record continues.
    ok_topology = _build(
        driver=_FastResponder(),
        first_user_text="opener (unused on resume)",
        session_id="s_fail",
        workspace=str(tmp_path / "ws"),
    )
    resume_event = UserMessage(
        text="recover please",
        turn_index=1,
        assembled_prompt="recover please",
        slash_source="test",
    )
    result_2 = await api.Runtime(root, persistent=True).resume(
        ok_topology, resume_event=resume_event
    )
    assert result_2.status == "paused", f"turn 2 expected paused, got {result_2.status}"

    envelopes = _read(root)
    user_msgs = _by_kind(envelopes, "UserMessage")
    assert len(user_msgs) == 2, f"expected 2 UserMessage after resume, got {len(user_msgs)}"
    assert user_msgs[1]["payload"]["text"] == "recover please"
    # A ModelReply from the successful turn now on the record.
    replies = _by_kind(envelopes, "ModelReply")
    assert replies, "expected a ModelReply on the resumed turn"
    # Park{final_answer} follows the successful turn (in addition to the earlier model_error).
    reasons_final = _park_reasons(envelopes)
    assert reasons_final.count("model_error") == 1
    assert "final_answer" in reasons_final, (
        f"expected Park{{final_answer}} after resume, got {reasons_final}"
    )


# ── test 2: park-on-interrupt ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_park_on_interrupt_then_resume(tmp_path: Path) -> None:
    """A slow model producer cancelled mid-turn → PRODUCER_CANCELLED{cause:external} →
    park-on-interrupt fires → Park{reason:"interrupt"}. Then resume with a working
    responder → the session continues cleanly on the same record.

    Sprint 244 closed the substrate-side gap: the model producer now awaits
    `driver.arespond`, so a slow driver yields the event loop and
    cancel_producer has a window to fire. This test is the observation
    contract for that fix + for TECH-SPEC §11's Ctrl+C promise.
    """
    root = tmp_path / "park-on-interrupt"

    slow_topology = _build(
        driver=_SlowResponder(delay=30.0),  # long enough for the interrupt to land
        first_user_text="take your time",
        session_id="s_interrupt",
        workspace=str(tmp_path / "ws"),
    )

    async def _interrupt_when_model_starts(runtime: api.Runtime) -> None:
        """Watch the runtime's own instance table until a model task is live,
        then cancel it. Reading `st.kind_by_instance` directly skips the
        record-write race the SSE-based watchers hit."""
        deadline = asyncio.get_event_loop().time() + 5.0
        while asyncio.get_event_loop().time() < deadline:
            st = getattr(runtime, "_st", None)
            if st is not None:
                for instance, kind in list(st.kind_by_instance.items()):
                    if kind != "model":
                        continue
                    task = st.task_by_instance.get(instance)
                    if task is None or task.done():
                        continue
                    result = runtime.cancel_producer(
                        instance, cause="external", caller="test:interrupt"
                    )
                    assert result is not None, (
                        f"cancel_producer returned None for live model instance {instance}"
                    )
                    return
            await asyncio.sleep(0.01)
        raise AssertionError("model producer never started within 5s — cannot interrupt")

    runtime = api.Runtime(root, persistent=True)
    interrupter = asyncio.create_task(_interrupt_when_model_starts(runtime))
    try:
        result_1 = await runtime.run(slow_topology)
    finally:
        interrupter.cancel()
        try:
            await interrupter
        except (asyncio.CancelledError, AssertionError):
            pass

    assert result_1.status == "paused", f"turn 1 expected paused, got {result_1.status}"

    envelopes = _read(root)
    cancels = _by_kind(envelopes, "substrate.ProducerCancelled")
    assert cancels, "expected substrate.ProducerCancelled after interrupt"
    model_cancels = [
        e for e in cancels if (e["payload"].get("producer") or {}).get("kind") == "model"
    ]
    assert model_cancels, "expected a model ProducerCancelled"
    # v0.3 provenance annotation lands.
    assert any(
        e["payload"].get("cause") == "external" and e["payload"].get("caller") == "test:interrupt"
        for e in model_cancels
    ), (
        f"expected cause=external/caller=test:interrupt on cancel payload, got {[(e['payload'].get('cause'), e['payload'].get('caller')) for e in model_cancels]}"
    )

    reasons = _park_reasons(envelopes)
    assert "interrupt" in reasons, f"expected Park{{interrupt}}, got {reasons}"

    # Resume path.
    ok_topology = _build(
        driver=_FastResponder(),
        first_user_text="opener (unused on resume)",
        session_id="s_interrupt",
        workspace=str(tmp_path / "ws"),
    )
    resume_event = UserMessage(
        text="continue please",
        turn_index=1,
        assembled_prompt="continue please",
        slash_source="test",
    )
    result_2 = await api.Runtime(root, persistent=True).resume(
        ok_topology, resume_event=resume_event
    )
    assert result_2.status == "paused", f"turn 2 expected paused, got {result_2.status}"

    envelopes = _read(root)
    assert len(_by_kind(envelopes, "UserMessage")) == 2
    reasons_final = _park_reasons(envelopes)
    assert "interrupt" in reasons_final and "final_answer" in reasons_final


# ── test 3: end-on-cap ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_end_on_cap_finalises_with_timeout_reason(tmp_path: Path) -> None:
    """max_turns=2. Turns 1 + 2 complete normally. The 3rd UserMessage bumps
    user_turns to 3 which exceeds max_turns=2, firing `end-on-cap` →
    SessionEnded{reason:"timeout", total_turns:2}. The run finalises."""
    root = tmp_path / "end-on-cap"

    # Turn 1 — first_turn_user_message opens the run.
    topo_1 = _build(
        driver=_FastResponder(),
        first_user_text="first message",
        session_id="s_cap",
        workspace=str(tmp_path / "ws"),
        max_turns=2,
    )
    result_1 = await api.Runtime(root, persistent=True).run(topo_1)
    assert result_1.status == "paused", f"turn 1 expected paused, got {result_1.status}"

    # Turn 2 — resume with the second UserMessage.
    topo_next = _build(
        driver=_FastResponder(),
        first_user_text="opener (unused on resume)",
        session_id="s_cap",
        workspace=str(tmp_path / "ws"),
        max_turns=2,
    )
    result_2 = await api.Runtime(root, persistent=True).resume(
        topo_next,
        resume_event=UserMessage(
            text="second message",
            turn_index=1,
            assembled_prompt="second message",
            slash_source="test",
        ),
    )
    assert result_2.status == "paused", f"turn 2 expected paused, got {result_2.status}"

    # Turn 3 — this one trips end-on-cap. The user_turns View counts to 3;
    # `end-on-cap` predicate is `> max_turns` (max_turns=2 → fires at 3);
    # session_end producer emits SessionEnded{timeout}; termination
    # threshold_count(SessionEnded, 1) matches; RunResult.status == "finalised".
    result_3 = await api.Runtime(root, persistent=True).resume(
        topo_next,
        resume_event=UserMessage(
            text="third message triggers cap",
            turn_index=2,
            assembled_prompt="third message triggers cap",
            slash_source="test",
        ),
    )
    assert result_3.status == "finalised", (
        f"turn 3 expected finalised (end-on-cap), got {result_3.status}"
    )

    envelopes = _read(root)
    session_ended = _by_kind(envelopes, "SessionEnded")
    assert len(session_ended) == 1, f"expected 1 SessionEnded, got {len(session_ended)}"
    assert session_ended[0]["payload"]["reason"] == "timeout", (
        f"expected reason=timeout, got {session_ended[0]['payload']}"
    )
    assert session_ended[0]["payload"]["total_turns"] == 2, (
        f"expected total_turns=2, got {session_ended[0]['payload']}"
    )

    # Record seals with substrate.RunFinalised.
    finalised = _by_kind(envelopes, "substrate.RunFinalised")
    assert finalised, "expected substrate.RunFinalised on the record"
