"""Rate-limit shim spike (design DESIGN-2026-08-11-responder-rate-limit-shim.md).

Three pure unit tests, no live network:
  1. Two wrappers with the same key share one semaphore — the gate is per-key,
     not per-wrapper.
  2. The wrapper honours Retry-After on 429 — a monkey-patched asyncio.sleep
     collects the sleeps and the total matches the header.
  3. After max_retries all rate-limit, the wrapper raises typed
     ProviderRateLimited, not RuntimeError.
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import httpx
import pytest

from substrate.adapters.rate_limit import (
    OllamaQuota,
    ProviderQuota,
    ProviderRateLimited,
    RateLimitedResponder,
    _reset_semaphores_for_tests,
    _semaphores,
)


@pytest.fixture(autouse=True)
def _clean_semaphores():
    _reset_semaphores_for_tests()
    yield
    _reset_semaphores_for_tests()


class _CountingResponder:
    """A Responder whose arespond blocks on an event so a test can hold requests
    open long enough to prove the semaphore counter matters."""

    def __init__(self):
        self.in_flight = 0
        self.peak_in_flight = 0
        self._release = asyncio.Event()

    def respond(self, prompt: str) -> str:  # pragma: no cover — sync unused here
        return "ok"

    async def arespond(self, prompt: str) -> str:
        self.in_flight += 1
        self.peak_in_flight = max(self.peak_in_flight, self.in_flight)
        try:
            await self._release.wait()
            return "ok"
        finally:
            self.in_flight -= 1

    def release(self) -> None:
        self._release.set()


class _Failing429Responder:
    """A Responder whose arespond always raises HTTPStatusError with a Retry-After."""

    def __init__(self, retry_after: str | None = "3"):
        self.attempts = 0
        self._retry_after = retry_after

    def respond(self, prompt: str) -> str:  # pragma: no cover
        return "unused"

    async def arespond(self, prompt: str) -> str:
        self.attempts += 1
        headers = {}
        if self._retry_after is not None:
            headers["Retry-After"] = self._retry_after
        response = httpx.Response(status_code=429, headers=headers)
        raise httpx.HTTPStatusError("rate-limited", request=MagicMock(), response=response)


def test_ollama_quota_tiers_match_public_docs():
    assert OllamaQuota.free().max_concurrent_per_model == 1
    assert OllamaQuota.pro().max_concurrent_per_model == 3
    assert OllamaQuota.max_tier().max_concurrent_per_model == 10
    assert OllamaQuota.local().max_concurrent_per_model == 16


def test_two_wrappers_share_semaphore_for_same_key():
    quota = ProviderQuota(max_concurrent_per_model=2)
    inner = _CountingResponder()
    a = RateLimitedResponder(inner, key="ollama:test-model", quota=quota)
    b = RateLimitedResponder(inner, key="ollama:test-model", quota=quota)

    async def _run():
        # Fire four concurrent requests split across the two wrappers. Cap is 2,
        # so peak_in_flight must never exceed 2.
        tasks = [
            asyncio.create_task(a.arespond("x")),
            asyncio.create_task(a.arespond("y")),
            asyncio.create_task(b.arespond("z")),
            asyncio.create_task(b.arespond("w")),
        ]
        await asyncio.sleep(0.05)  # let scheduling settle
        assert inner.in_flight <= 2, "gate should cap at 2 across both wrappers"
        assert inner.peak_in_flight == 2
        inner.release()
        await asyncio.gather(*tasks)

    asyncio.run(_run())


def test_wrapper_honours_retry_after_header():
    quota = ProviderQuota(max_concurrent_per_model=1, max_retries=3)
    inner = _Failing429Responder(retry_after="2")
    wrapper = RateLimitedResponder(inner, key="ollama:rate-hit", quota=quota)

    sleeps: list[float] = []

    async def _fake_sleep(delay: float):
        sleeps.append(delay)

    async def _run():
        import substrate.adapters.rate_limit as rl_module

        real_sleep = asyncio.sleep
        rl_module.asyncio.sleep = _fake_sleep  # type: ignore[assignment]
        try:
            with pytest.raises(ProviderRateLimited):
                await wrapper.arespond("prompt")
        finally:
            rl_module.asyncio.sleep = real_sleep  # type: ignore[assignment]

    asyncio.run(_run())
    # Three attempts fail, so three sleep calls — all should honour the header (2.0s).
    assert sleeps == [2.0, 2.0, 2.0], f"expected Retry-After=2 honoured, got {sleeps}"
    assert inner.attempts == 3


def test_wrapper_raises_typed_after_exhaustion():
    quota = ProviderQuota(max_concurrent_per_model=1, max_retries=2)
    inner = _Failing429Responder(retry_after="0")
    wrapper = RateLimitedResponder(inner, key="ollama:exhausted", quota=quota)

    async def _run():
        with pytest.raises(ProviderRateLimited) as excinfo:
            await wrapper.arespond("prompt")
        assert excinfo.value.key == "ollama:exhausted"
        assert excinfo.value.attempts == 2

    asyncio.run(_run())


def test_semaphore_key_isolation():
    quota = ProviderQuota(max_concurrent_per_model=1)
    inner_a = _CountingResponder()
    inner_b = _CountingResponder()
    a = RateLimitedResponder(inner_a, key="ollama:model-a", quota=quota)
    b = RateLimitedResponder(inner_b, key="ollama:model-b", quota=quota)

    async def _run():
        # Different keys => independent semaphores. Both should be in-flight at once
        # even though each key's cap is 1.
        ta = asyncio.create_task(a.arespond("x"))
        tb = asyncio.create_task(b.arespond("y"))
        await asyncio.sleep(0.05)
        assert inner_a.in_flight == 1
        assert inner_b.in_flight == 1
        inner_a.release()
        inner_b.release()
        await asyncio.gather(ta, tb)

    asyncio.run(_run())
    # Two distinct semaphores registered.
    assert "ollama:model-a" in _semaphores
    assert "ollama:model-b" in _semaphores
    assert _semaphores["ollama:model-a"] is not _semaphores["ollama:model-b"]
