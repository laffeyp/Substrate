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
    envelopes = list(api.read_record(record_root))
    user_messages = [e for e in envelopes if e["kind"] == "UserMessage"]
    assert len(user_messages) == 10
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
    assert comp.dropped_seq_range[0] == user_messages[0]["seq"]
    assert comp.kept_seq_start == user_messages[5]["seq"]
    assert comp.dropped_seq_range[1] < comp.kept_seq_start


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
