# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""per_turn fragment source — sprint 060 tests.

Verifies:
 - The per_turn producer yields exactly one PromptFragment per UserMessage
   when manifest.per_turn is non-empty.
 - Empty per_turn produces zero fragments (empty-body producer completes
   without yield).
 - Fragment payload carries source=per_turn, text=<per_turn value>,
   precedence=10, provenance={}.
 - PATCH-through-session-life: a mid-session per_turn change surfaces on
   the next turn (deferred to piece B tests; this file exercises the
   Producer-level shape, not the daemon path).

Deferred to sprint 064: dual-path removal (render_transcript stops
injecting per_turn) and the live-model assertion that the fragment (not
the render-side injection) is what drives the model.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from substrate import api
from substrate.topologies.session.ci import ci_session_topology


def test_per_turn_fragment_lands_when_per_turn_set(tmp_path: Path) -> None:
    """A three-turn CI session with per_turn="MARK" produces three
    PromptFragment(source=per_turn) events on the record — one per
    UserMessage."""

    async def _run() -> None:
        record_root = tmp_path / "ci"
        topology = ci_session_topology(
            turns=("hi", "count to five", "/exit"),
            session_id="s_per_turn_set",
            per_turn="MARK-PER-TURN",
        )
        await api.Runtime(record_root).run(topology)

    asyncio.run(_run())
    envs = list(api.read_record(tmp_path / "ci"))
    fragments = [e for e in envs if e.get("kind") == "PromptFragment"]
    per_turn_fragments = [e for e in fragments if e["payload"].get("source") == "per_turn"]
    assert len(per_turn_fragments) == 3, (
        f"expected 3 per_turn fragments (one per UserMessage), got {len(per_turn_fragments)}"
    )
    for env in per_turn_fragments:
        payload = env["payload"]
        assert payload["text"] == "MARK-PER-TURN"
        assert payload["precedence"] == 10
        assert payload["provenance"] == {}


def test_per_turn_fragment_empty_when_per_turn_absent(tmp_path: Path) -> None:
    """A session with per_turn="" (the ci_session_topology default) produces
    ZERO PromptFragment(source=per_turn) events. The empty-body producer
    completes without yielding."""

    async def _run() -> None:
        record_root = tmp_path / "ci"
        topology = ci_session_topology(
            turns=("hi", "/exit"),
            session_id="s_per_turn_empty",
        )
        await api.Runtime(record_root).run(topology)

    asyncio.run(_run())
    envs = list(api.read_record(tmp_path / "ci"))
    fragments = [e for e in envs if e.get("kind") == "PromptFragment"]
    per_turn_fragments = [e for e in fragments if e["payload"].get("source") == "per_turn"]
    assert len(per_turn_fragments) == 0, (
        f"expected 0 per_turn fragments when per_turn empty, got {len(per_turn_fragments)}"
    )


def test_per_turn_fragment_survives_replay(tmp_path: Path) -> None:
    """A second run against the same topology + turns produces a byte-
    reproducible record on the fragment side too. Fragment payloads,
    precedence, and count all match across the two runs.
    """

    async def _run(dest: Path) -> None:
        topology = ci_session_topology(
            turns=("hi", "/exit"),
            session_id="s_per_turn_replay",
            per_turn="LOCK",
        )
        await api.Runtime(dest).run(topology)

    asyncio.run(_run(tmp_path / "a"))
    asyncio.run(_run(tmp_path / "b"))
    envs_a = list(api.read_record(tmp_path / "a"))
    envs_b = list(api.read_record(tmp_path / "b"))
    frags_a = [
        e["payload"]
        for e in envs_a
        if e.get("kind") == "PromptFragment" and e["payload"].get("source") == "per_turn"
    ]
    frags_b = [
        e["payload"]
        for e in envs_b
        if e.get("kind") == "PromptFragment" and e["payload"].get("source") == "per_turn"
    ]
    assert frags_a == frags_b
    assert len(frags_a) == 2  # one per UserMessage in ("hi", "/exit")
