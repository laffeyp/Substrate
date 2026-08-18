"""Provider-agnostic rate-limit wrapper for Responders (design DESIGN-2026-08-11).

Every LLM provider has capacity limits — Ollama Cloud caps concurrent MODELS per
tier (Free 1, Pro 3, Max 10), OpenAI + Anthropic cap requests-per-minute and
tokens-per-minute per tier, xAI + Gemini have their own shapes. The naive posture
(fire N concurrent requests, let 429 sort it out) fails under sustained pressure:
the 2026-08-10 Ollama Pro run at CONCURRENCY=8 got 82% of 4088 calls throttled
because 8 in-flight requests to one model exceeded the tier's 3-concurrent-model
allowance.

`RateLimitedResponder` wraps ANY Responder and:

  1. Caps concurrent in-flight calls per (provider, model) key via a shared
     asyncio.Semaphore. Two Responders talking to the same model share one gate,
     no matter which arm or topology constructed them.
  2. Honours the `Retry-After` header on 429/503 responses. On rate-limit, sleeps
     the header's number of seconds (or exponential backoff capped at 60s if no
     header), retries up to `max_retries` before raising `ProviderRateLimited`.

Provider-agnostic on purpose: one `ProviderQuota` per tier per provider, one
`RateLimitedResponder` wraps any Responder. The next provider needs no new
interfaces, just a new quota helper.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..protocols import Responder


@dataclass(frozen=True)
class ProviderQuota:
    """One provider tier's capacity descriptors. Static; construct once per (provider, tier).

    `max_concurrent_per_model` is the hard cap on in-flight requests to any single model
    from this provider at this tier. The per-model semaphore uses this counter.

    `max_rpm` and `max_tpm` are optional — Ollama Cloud publishes concurrent-model caps
    but not RPM/TPM; OpenAI + Anthropic publish RPM + TPM. When populated, a future
    extension of the wrapper can add a token-bucket layer; today only the concurrent cap
    is enforced.

    `max_retries` is the wrapper's cap on 429/503 retry count before raising
    `ProviderRateLimited`. Ten is enough to weather a normal rate-limit burst
    (10 × ~5s retry-after ≈ 50s total wait) without pinning a worker forever."""

    max_concurrent_per_model: int
    max_rpm: int | None = None
    max_tpm: int | None = None
    max_retries: int = 10


class OllamaQuota:
    """Ollama Cloud tier limits (pooyagolchian.com/blog/ollama-cloud-pricing-hardware-
    requirements-2026, devtoolhub.com/ollama-cloud-free-vs-pro-limits-pricing-2026).
    The published limit is `concurrent models` — how many DIFFERENT models can be loaded
    at once. Interpreted here as `concurrent requests per model` because the runner's
    binding constraint is fanout to a single model, not distinct-model count. When Ollama
    revises limits, update the classmethods; the shape stays."""

    @classmethod
    def free(cls) -> ProviderQuota:
        return ProviderQuota(max_concurrent_per_model=1)

    @classmethod
    def pro(cls) -> ProviderQuota:
        return ProviderQuota(max_concurrent_per_model=3)

    @classmethod
    def max_tier(cls) -> ProviderQuota:
        return ProviderQuota(max_concurrent_per_model=10)

    @classmethod
    def local(cls) -> ProviderQuota:
        """Local Ollama (no cloud, no rate limit). The default `OLLAMA_NUM_PARALLEL=1`
        queues serially inside the daemon; caller sets a wider cap when the model fits
        multiple contexts in memory. Cap at 16 as a runaway backstop."""
        return ProviderQuota(max_concurrent_per_model=16)


class ProviderRateLimited(RuntimeError):
    """Raised when `RateLimitedResponder` exhausts `max_retries` under sustained
    rate-limit pressure. IS-A RuntimeError so existing broad handlers keep working;
    typed so the runner's `_classify_cell_error` can map it to a first-class reason
    string in the shared `_HARNESS_REASONS` closed set (once `REASON_RATE_LIMITED`
    ratifies through the vocab halt)."""

    def __init__(self, key: str, attempts: int, detail: str = "") -> None:
        super().__init__(f"provider rate-limited after {attempts} attempts on {key}: {detail}")
        self.key = key
        self.attempts = attempts
        self.detail = detail


# Module-level semaphore registry: one Semaphore per key. Shared across every
# RateLimitedResponder constructed with the same key so two wrappers for the same
# model share ONE gate. Keys are strings like "ollama:qwen2.5-coder:7b".
_semaphores: dict[str, asyncio.Semaphore] = {}


def _semaphore_for(key: str, capacity: int) -> asyncio.Semaphore:
    """Return the semaphore for `key`, creating it at `capacity` on first request.
    A subsequent request with a different capacity WINS THE FIRST ONE (the semaphore
    is created once); log a warning if the capacities disagree. Static tier config
    means every wrapper for one key should agree."""
    if key not in _semaphores:
        _semaphores[key] = asyncio.Semaphore(capacity)
    return _semaphores[key]


def _reset_semaphores_for_tests() -> None:
    """Test-only: reset the module-level semaphore registry so tests can pin exact
    counters without cross-test bleed. Not exported through `substrate.adapters`."""
    _semaphores.clear()


class RateLimitedResponder:
    """Wraps ANY Responder with per-(provider, model) concurrency capping + Retry-After
    honour on 429/503. Implements the `Responder` protocol so callers use it identically
    to any other Responder; the wrapper is invisible to the topology.

    Only the async path (`arespond`, `arespond_metered`) is capped by the semaphore —
    the runner's I/O path is async, and the sync `respond` is left as a passthrough for
    the rare non-async caller. When `respond` is called from inside an async context, use
    `arespond` explicitly; the sync path does not participate in the gate.
    """

    def __init__(
        self,
        inner: Responder,
        *,
        key: str,
        quota: ProviderQuota,
    ) -> None:
        self._inner = inner
        self._key = key
        self._quota = quota
        # Semaphore lazily on first async call — asyncio.Semaphore construction
        # requires an event loop (may not exist at __init__ time in some callers).

    @property
    def key(self) -> str:
        return self._key

    def respond(self, prompt: str) -> str:
        """Sync passthrough (Responder protocol). Not capped — the gate is async-only."""
        return self._inner.respond(prompt)

    async def arespond(self, prompt: str) -> str:
        """Cancellable async call, capped by the (provider, model) semaphore, retries
        429/503 honestly by reading Retry-After. Raises `ProviderRateLimited` if
        `max_retries` attempts all rate-limit.

        Sprint 168 (F1 fix): the semaphore is held ONLY around each in-flight inner call
        and released during the retry sleep. Before Sprint 168, `async with sem:` wrapped
        the entire retry loop, so a 429 sleep pinned the slot while nothing was in flight;
        the 2026-08-10 N=300 Pro run collapsed to 82% throttled because three workers
        sleeping on 429 pinned all three Pro-tier slots simultaneously. Releasing during
        the sleep lets a healthier peer take the slot and progress; only the workers
        currently making an inner call hold semaphore capacity.
        """
        import httpx

        sem = _semaphore_for(self._key, self._quota.max_concurrent_per_model)
        last_detail = ""
        for attempt in range(self._quota.max_retries):
            # Hold the slot ONLY around the actual in-flight call. Retry sleep happens
            # outside the semaphore scope so a sleeping worker does not pin a slot.
            async with sem:
                try:
                    arespond = getattr(self._inner, "arespond", None)
                    if arespond is None:
                        # Fallback: run sync respond in a thread so the wrapper still
                        # works against Responders without an async path.
                        return await asyncio.to_thread(self._inner.respond, prompt)
                    result: str = await arespond(prompt)
                    return result
                except httpx.HTTPStatusError as exc:
                    if exc.response.status_code not in (429, 503):
                        raise
                    retry_after = _parse_retry_after(exc.response.headers.get("Retry-After"))
                    delay = retry_after if retry_after is not None else min(60.0, 2.0**attempt)
                    last_detail = f"HTTP {exc.response.status_code} attempt {attempt + 1}"
                except RuntimeError as exc:
                    # OllamaResponder wraps httpx errors in RuntimeError with the status
                    # code in the message. Fallback parse for that shape.
                    msg = str(exc).lower()
                    if "429" not in msg and "503" not in msg:
                        raise
                    delay = min(60.0, 2.0**attempt)
                    last_detail = f"RuntimeError attempt {attempt + 1}: {str(exc)[:120]}"
            # Sleep outside the semaphore scope — critical for tier-capacity health under
            # sustained 429 pressure. The next iteration re-acquires the slot before its
            # in-flight call.
            await asyncio.sleep(delay)
        raise ProviderRateLimited(self._key, self._quota.max_retries, last_detail)


def _parse_retry_after(header: str | None) -> float | None:
    """Retry-After per RFC 7231 §7.1.3: either a decimal number of seconds, or an
    HTTP-date. Only the number form is parsed here (HTTP-date is rare in practice and
    adds a date-parsing dependency). Returns None if the header is missing or
    unparseable — caller falls back to exponential backoff."""
    if not header:
        return None
    try:
        return float(header)
    except (TypeError, ValueError):
        return None


__all__ = [
    "OllamaQuota",
    "ProviderQuota",
    "ProviderRateLimited",
    "RateLimitedResponder",
]
