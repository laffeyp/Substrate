"""Integration test for Runtime.cancel_producers — the cancel-by-kind API (sprint 215b).

Verifies: a long-running producer started with kind "slow" is cancelled via
`runtime.cancel_producers("slow")`, producing a ProducerCancelled event on the record.
"""

from __future__ import annotations

import asyncio

import pytest
from msgspec import Struct

from substrate import api
from substrate.constants import PRODUCER_CANCELLED


class Tick(Struct, frozen=True):
    n: int


async def _slow_producer(_input: object) -> object:
    for i in range(1, 1000):
        await asyncio.sleep(0.5)
        yield Tick(n=i)


@pytest.fixture
def record_root(tmp_path):
    return tmp_path / "cancel-test"


@pytest.mark.asyncio
async def test_cancel_producers_records_cancelled_event(record_root):
    """Start a slow producer, cancel it by kind, confirm ProducerCancelled lands."""

    runtime = api.Runtime(record_root)
    cancel_fired = asyncio.Event()

    def topo(b):
        b.producer_kind("slow", schemas=[Tick], schema_version=1, factory=lambda: _slow_producer)
        b.initial("slow", input=None)
        b.termination(api.quiescence_with_watchdog(seconds=5))

    async def _cancel_after_start():
        # wait for the producer to start (give it time to begin sleeping)
        await asyncio.sleep(0.2)
        n = runtime.cancel_producers("slow")
        assert n == 1, f"expected 1 cancel, got {n}"
        cancel_fired.set()

    task = asyncio.create_task(runtime.run(topo))
    cancel_task = asyncio.create_task(_cancel_after_start())

    result = await task
    await cancel_task

    assert result.status in ("finalised", "paused"), f"unexpected status: {result.status}"

    envs = list(api.read_record(record_root))
    cancelled = [e for e in envs if e["kind"] == PRODUCER_CANCELLED]
    assert len(cancelled) == 1, f"expected 1 ProducerCancelled, got {len(cancelled)}"
    ref = cancelled[0]["payload"]["producer"]
    assert ref["kind"] == "slow"
