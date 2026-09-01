# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Sprint 207 — TranscriptCompacted seq math against a real on-disk record.

The unit tests in `test_render_rolling_window_basic.py` and
`test_render_no_compaction.py` monkeypatch `read_record`. This test writes a real
persistent record through the runtime, then re-reads it through `read_record`
and calls `render_transcript` against the on-disk root. It proves the renderer
integrates with the real record IO path — segment sealing, envelope framing,
seq contiguity — not just against a synthetic list.

Model / park / session_end producer bodies wire in later sprints; this test
opens the topology only to write a small deterministic sequence of typed events
by driving a Producer-of-fixture. That producer emits UserMessage + ModelReply
pairs directly, bypassing the scaffolded model factory.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any

import pytest

from substrate import api
from substrate.testing import assert_event
from substrate.topologies.session import ModelReply, UserMessage
from substrate.topologies.session.transcript import render_transcript


def _fixture_writer(
    turns: int,
) -> Callable[[], Callable[[Any], AsyncIterator[UserMessage | ModelReply]]]:
    async def producer(inp: Any) -> AsyncIterator[UserMessage | ModelReply]:
        del inp
        for turn_index in range(turns):
            yield UserMessage(
                text=f"hello {turn_index}",
                turn_index=turn_index,
                assembled_prompt=f"h{turn_index}",
                slash_source=None,
            )
            yield ModelReply(
                text=f"reply {turn_index}",
                model_usage={"prompt_tokens": 10, "completion_tokens": 5},
                turn_index=turn_index,
            )

    return lambda: producer


def _fixture_topology(turns: int) -> Callable[[api.TopologyBuilder], None]:
    def topo(b: api.TopologyBuilder) -> None:
        b.producer_kind(
            "seed",
            schemas=[UserMessage, ModelReply],
            schema_version=1,
            factory=_fixture_writer(turns),
            deterministic=True,
        )
        b.initial("seed", input={})
        b.termination(api.threshold_count("ModelReply", turns))

    return topo


@pytest.mark.asyncio
async def test_transcript_compacted_seqs_match_on_real_record(tmp_path: Path) -> None:
    record_root = tmp_path / "session"
    await api.Runtime(record_root).run(_fixture_topology(turns=10))
    # Anchor the first + sixth UserMessage seqs via F-API-4 primitives; assert_event
    # returns the matching envelope so the seq math below stays record-derived.
    first_user = assert_event(record_root, "UserMessage", turn_index=0)
    kept_head_user = assert_event(record_root, "UserMessage", turn_index=5)
    result = render_transcript(
        record_root=record_root,
        seed="",
        per_turn="",
        driver_context_tokens=6667,  # forces K = 5 (see basic test for the arithmetic)
        turn_index_now=10,
    )
    assert result.turns_dropped == 5
    assert len(result.compaction_events) == 1
    comp = result.compaction_events[0]
    assert comp.dropped_seq_range[0] == first_user["seq"]
    assert comp.kept_seq_start == kept_head_user["seq"]
    assert comp.dropped_seq_range[1] < comp.kept_seq_start
    # The fixture producer is deterministic; the record must replay byte-identical.
    api.assert_replayable(record_root, "3a")


@pytest.mark.asyncio
async def test_no_transcript_compacted_on_short_real_record(tmp_path: Path) -> None:
    record_root = tmp_path / "short"
    await api.Runtime(record_root).run(_fixture_topology(turns=3))
    result = render_transcript(
        record_root=record_root,
        seed="",
        per_turn="",
        driver_context_tokens=200_000,
        turn_index_now=3,
    )
    assert result.turns_dropped == 0
    assert result.compaction_events == []
    api.assert_replayable(record_root, "3a")
