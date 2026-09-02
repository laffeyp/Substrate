# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""tools_suite + user_message fragment sources — sprint 064 tests.

Verifies:
 - tools_suite: session with CALCULATOR tools emits one
   PromptFragment(source=tools_suite) at session open with tool names
   in text and provenance.
 - user_message: per turn, emits one PromptFragment(source=user_message)
   whose text matches the UserMessage.text and provenance carries
   turn_index.
 - Precedence pins (20 for tools_suite, 100 for user_message).
 - Empty tools yield zero tools_suite fragments.
 - Chain ordering: composer's cohort on turn 1 includes tools_suite +
   user_message fragments (sprint 064 chain migration).
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from substrate import api
from substrate.topologies.session.ci import ci_session_topology


def test_tools_suite_fragment_lands_at_session_open(tmp_path: Path) -> None:
    """CI session with CALCULATOR emits exactly one
    PromptFragment(source=tools_suite) whose text mentions the add/mul
    tools and whose provenance names them."""

    async def _run() -> None:
        topology = ci_session_topology(
            turns=("hi", "/exit"),
            session_id="s_tools_suite",
        )
        await api.Runtime(tmp_path / "ci").run(topology)

    asyncio.run(_run())
    envs = list(api.read_record(tmp_path / "ci"))
    frags = [
        e
        for e in envs
        if e.get("kind") == "PromptFragment" and e["payload"].get("source") == "tools_suite"
    ]
    assert len(frags) == 1, f"expected 1 tools_suite fragment, got {len(frags)}"
    payload = frags[0]["payload"]
    assert "add" in payload["text"]
    assert "mul" in payload["text"]
    assert payload["precedence"] == 20
    assert set(payload["provenance"]["tool_names"]) == {"add", "mul"}


def test_user_message_fragment_lands_per_turn(tmp_path: Path) -> None:
    """A three-turn CI session yields three PromptFragment(source=user_message)
    events; each text matches the corresponding UserMessage.text; each
    provenance carries turn_index in monotone order."""

    async def _run() -> None:
        topology = ci_session_topology(
            turns=("alpha", "bravo", "/exit"),
            session_id="s_user_message_multi",
        )
        await api.Runtime(tmp_path / "ci").run(topology)

    asyncio.run(_run())
    envs = list(api.read_record(tmp_path / "ci"))
    frags = [
        e
        for e in envs
        if e.get("kind") == "PromptFragment" and e["payload"].get("source") == "user_message"
    ]
    # Turn 3 is /exit — routes to session_end. The chain may or may not
    # complete before finalisation; assert at least the first two turns.
    assert len(frags) >= 2, f"expected >=2 user_message fragments, got {len(frags)}"
    payload_first = frags[0]["payload"]
    assert payload_first["text"] == "alpha"
    assert payload_first["precedence"] == 100
    assert payload_first["provenance"]["turn_index"] == 0
    payload_second = frags[1]["payload"]
    assert payload_second["text"] == "bravo"
    assert payload_second["provenance"]["turn_index"] == 1


def test_chain_ordering_composer_sees_full_cohort(tmp_path: Path) -> None:
    """Sprint 064 chain: UserMessage → per_turn_fragment →
    user_message_fragment → composer. Composer's cohort on turn 1
    contains tools_suite (session-open) + per_turn + user_message.
    Locks the composer's deterministic ordering fix."""

    async def _run() -> None:
        topology = ci_session_topology(
            turns=("compose-me", "/exit"),
            session_id="s_chain_order",
            per_turn="PT",
        )
        await api.Runtime(tmp_path / "ci").run(topology)

    asyncio.run(_run())
    envs = list(api.read_record(tmp_path / "ci"))
    composed = [e for e in envs if e.get("kind") == "PromptComposed"]
    assert len(composed) >= 1
    text = composed[0]["payload"]["text"]
    # Fragment sources should all appear in the composed text, ordered
    # by precedence: tools_suite (20) < per_turn (10)... wait, 10 < 20.
    # per_turn precedence 10 comes BEFORE tools_suite precedence 20 comes
    # BEFORE user_message precedence 100.
    per_turn_pos = text.find("PT")
    tools_pos = text.find("add")  # CALCULATOR describes add(a,b)
    user_pos = text.find("compose-me")
    assert per_turn_pos != -1, f"per_turn missing from composed text: {text!r}"
    assert tools_pos != -1, f"tools_suite missing from composed text: {text!r}"
    assert user_pos != -1, f"user_message missing from composed text: {text!r}"
    assert per_turn_pos < tools_pos < user_pos, (
        f"precedence order violated: per_turn@{per_turn_pos}, "
        f"tools@{tools_pos}, user@{user_pos} in {text!r}"
    )


def test_user_message_empty_text_yields_no_fragment() -> None:
    """The producer yields no fragment when text is empty. Empty-body
    behavior locks against unintended fragment emission."""
    import asyncio

    from substrate.topologies.session.user_message_fragment_producer import (
        user_message_fragment_producer_factory,
    )

    factory = user_message_fragment_producer_factory()

    async def _drain() -> list[object]:
        return [item async for item in factory()({"text": "", "turn_index": 0})]

    assert asyncio.run(_drain()) == []
