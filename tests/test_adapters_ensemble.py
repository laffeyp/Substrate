"""EnsembleResponder — sprint 157b.

Pins round-robin cycling across N backends on both the sync and async paths, the metered
fallback for backends that don't implement `respond_metered`, and the boundary cases (empty
list rejected; single-backend degenerates to always-that-backend).
"""

from __future__ import annotations

import pytest

from substrate.adapters import EnsembleResponder
from substrate.adapters.models import ModelUsage


class _Stub:
    """A Responder that records every call it received and returns a fixed marker so a caller
    can verify which backend served which call."""

    def __init__(self, marker: str) -> None:
        self.marker = marker
        self.calls: list[str] = []

    def respond(self, prompt: str) -> str:
        self.calls.append(prompt)
        return f"{self.marker}:{prompt}"


class _MeteredStub(_Stub):
    """A stub that also implements the metered paths so the ensemble's forwarding branch is
    exercised."""

    def respond_metered(self, prompt: str) -> tuple[str, ModelUsage]:
        text = self.respond(prompt)
        return text, ModelUsage(
            prompt_tokens=1,
            completion_tokens=2,
            wall_ms=3,
            model=self.marker,
            estimated=False,  # provider-truth marker — the ensemble must preserve this
        )

    async def arespond(self, prompt: str) -> str:
        return self.respond(prompt)

    async def arespond_metered(self, prompt: str) -> tuple[str, ModelUsage]:
        return self.respond_metered(prompt)


def test_empty_backing_list_is_rejected():
    # An ensemble of zero responders can't route anything — fail loudly, not silently.
    with pytest.raises(ValueError, match="at least one"):
        EnsembleResponder([])


def test_respond_cycles_round_robin_across_backends():
    a, b, c = _Stub("a"), _Stub("b"), _Stub("c")
    ens = EnsembleResponder([a, b, c])
    # Five calls should distribute a, b, c, a, b — round-robin from index 0, deterministic.
    outs = [ens.respond(f"p{i}") for i in range(5)]
    assert outs == ["a:p0", "b:p1", "c:p2", "a:p3", "b:p4"]
    assert a.calls == ["p0", "p3"]
    assert b.calls == ["p1", "p4"]
    assert c.calls == ["p2"]


def test_len_reports_backend_count():
    ens = EnsembleResponder([_Stub("a"), _Stub("b")])
    assert len(ens) == 2


def test_single_backend_degenerate_case_always_that_backend():
    # A 1-element ensemble is a legitimate degenerate case (a caller might build the arm
    # generically and only sometimes supply multiple models). Every call goes to the sole
    # backend; not an error.
    only = _Stub("solo")
    ens = EnsembleResponder([only])
    for i in range(3):
        assert ens.respond(f"p{i}") == f"solo:p{i}"
    assert only.calls == ["p0", "p1", "p2"]


def test_respond_metered_forwards_when_backend_implements_it():
    a, b = _MeteredStub("a"), _MeteredStub("b")
    ens = EnsembleResponder([a, b])
    text_a, usage_a = ens.respond_metered("p0")
    text_b, usage_b = ens.respond_metered("p1")
    assert text_a == "a:p0"
    assert text_b == "b:p1"
    # provider-truth marker preserved end-to-end (the aggregator relies on it — sprint 144a #8).
    assert usage_a.estimated is False and usage_b.estimated is False
    assert usage_a.model == "a" and usage_b.model == "b"


def test_respond_metered_falls_back_to_standin_when_backend_lacks_metered():
    # A backend without `respond_metered` (a plain _Stub) still works — the ensemble synthesises
    # a stand-in ModelUsage marked `estimated=True` so the aggregator can distinguish it from
    # provider-truth.
    only = _Stub("plain")
    ens = EnsembleResponder([only])
    text, usage = ens.respond_metered("hello world")
    assert text == "plain:hello world"
    assert usage.estimated is True
    assert usage.model == "ensemble-standin"
    # Stand-in token counts are word-count approximations; not exact but roughly proportional.
    assert usage.prompt_tokens == 2  # "hello world"
    assert usage.completion_tokens == 2  # "plain:hello world" -> word-split


async def test_arespond_cycles_across_async_backends(tmp_path):  # type: ignore[no-untyped-def]
    a, b = _MeteredStub("a"), _MeteredStub("b")
    ens = EnsembleResponder([a, b])
    out_a = await ens.arespond("p0")
    out_b = await ens.arespond("p1")
    out_a2 = await ens.arespond("p2")
    assert out_a == "a:p0"
    assert out_b == "b:p1"
    assert out_a2 == "a:p2"


async def test_arespond_metered_cycles_across_async_backends():  # type: ignore[no-untyped-def]
    a, b, c = _MeteredStub("a"), _MeteredStub("b"), _MeteredStub("c")
    ens = EnsembleResponder([a, b, c])
    outs = []
    for i in range(6):
        text, usage = await ens.arespond_metered(f"p{i}")
        outs.append((text, usage.model))
    assert outs == [
        ("a:p0", "a"),
        ("b:p1", "b"),
        ("c:p2", "c"),
        ("a:p3", "a"),
        ("b:p4", "b"),
        ("c:p5", "c"),
    ]


async def test_arespond_falls_back_to_sync_when_backend_lacks_async():  # type: ignore[no-untyped-def]
    # A sync-only backend (a plain _Stub) works on the async path via the sync `respond` fallback.
    only = _Stub("sync-only")
    ens = EnsembleResponder([only])
    assert await ens.arespond("hello") == "sync-only:hello"


async def test_arespond_metered_falls_back_to_sync_and_synthesises_standin():  # type: ignore[no-untyped-def]
    only = _Stub("sync-only")
    ens = EnsembleResponder([only])
    text, usage = await ens.arespond_metered("hi there")
    assert text == "sync-only:hi there"
    assert usage.estimated is True
    assert usage.model == "ensemble-standin"


def test_counter_persists_across_call_kinds():
    # Round-robin cycles across MIXED call kinds — a sync respond followed by an async arespond
    # should keep advancing the same counter, not reset per method.
    a, b = _MeteredStub("a"), _MeteredStub("b")
    ens = EnsembleResponder([a, b])
    assert ens.respond("p0") == "a:p0"
    # Next call is arespond — must land on B, not restart at A.
    import asyncio

    assert asyncio.run(ens.arespond("p1")) == "b:p1"
