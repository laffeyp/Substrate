"""The dual-mode model seam for the reference topologies (product §8).

Every reference topology is dual-mode: a CI mode with DETERMINISTIC stand-in Producers
(proves the wiring, runs every commit, no network) and a WALKTHROUGH mode with real local
LLMs (proves the claim — adjudication in R-1, overlap in R-3). The seam is a `Responder`:
`respond(prompt) -> str`. Topologies are written against the Responder, not against any
model; the mode is chosen by which Responder the run is handed.

  - DeterministicResponder — canned, seed-derived answers; pure, no I/O. The CI mode. The
    spec is explicit that CI mode alone "sanitizes away the thing each topology exists to
    demonstrate", so CI mode proves WIRING only and never masquerades as the demonstration.
  - OllamaResponder — a real call to Ollama's native /api/chat (http://localhost:11434 by
    default) over httpx (the `openai-compat` optional extra; the kernel imports none of it —
    httpx is imported lazily here). Sets think=False + num_ctx + retry, the things a real model
    actually needs to work (a naive single-shot call silently breaks reasoning models and
    long transcripts). The WALKTHROUGH mode.

Local models only: the walkthrough uses llama3.2:1b (weak ensemble members / quick runs)
and huihui_ai/qwen2.5-coder-abliterate:7b (R-1 adjudicator / R-3 writer); cloud models are
avoided (the demonstration runs on the Architect's machine).
"""

from __future__ import annotations

import asyncio
import hashlib

from msgspec import Struct

# The Responder Protocol now lives among the structural protocols (substrate.protocols) and is
# public as substrate.api.Responder; re-exported here so `from substrate.reference import
# Responder` and the topologies' `from ..reference._models import Responder` keep working.
from ..protocols import Responder

__all__ = [
    "Responder",
    "DeterministicResponder",
    "OllamaResponder",
    "call_responder",
    "ModelUsage",
    "call_responder_metered",
]


class ModelUsage(Struct, frozen=True):
    """Per-model-call resource usage, emitted as an application event at the Responder seam so token
    counts and latency land on the inner record — the measurement the seam used to throw away.
    Tokens + wall time + the model id. No money is tracked anywhere: these are local / subscription
    models, so there is no per-call dollar amount and never will be. A
    DeterministicResponder reports wall_ms=0 and word-count token estimates so a CI record stays
    byte-stable; a real OllamaResponder reports Ollama's own prompt_eval_count / eval_count and an
    inference-only wall time. `estimated` is True when the counts are a word-count stand-in rather
    than provider truth, so a reader tells them apart from the DATA, not by parsing the model string.
    All fields RFC-8785-encodable, so the event rides the bus like any other application kind
    (Producer-declared, not a reserved substrate.* kind — the ToolCall precedent)."""

    model: str
    prompt_tokens: int
    completion_tokens: int
    wall_ms: int  # INFERENCE latency (prompt-eval + generation); excludes model load — see _usage
    estimated: bool = False  # True = word-count stand-in, not provider truth

    def total_tokens(self) -> int:
        """prompt + completion. A method, not a field, so it never lands on the wire (the durable
        facts are the two counts; the sum is derived)."""
        return self.prompt_tokens + self.completion_tokens


class DeterministicResponder:
    """A pure, seeded stand-in (CI mode). Same prompt + seed => same answer, no network — so
    the topology's WIRING is exercised reproducibly and replay/D-8 hold. It does NOT pretend
    to reason; it returns a stable canned answer derived from (seed, prompt, optional menu).
    The spec requires CI mode to never masquerade as the real demonstration; this responder is
    deliberately trivial so no one mistakes its output for model output."""

    def __init__(self, seed: int = 0, menu: list[str] | None = None) -> None:
        self._seed = seed
        self._menu = menu

    def respond(self, prompt: str) -> str:
        h = hashlib.sha256(f"{self._seed}:{prompt}".encode()).hexdigest()
        if self._menu:
            return self._menu[int(h[:8], 16) % len(self._menu)]
        return f"stub[{self._seed}]:{h[:12]}"


class OllamaResponder:
    """A real local-LLM responder over Ollama's native `/api/chat` (walkthrough mode).

    Rebuilt to the standard a precursor orchestrator proved is REQUIRED to make open-source models
    actually work — a naive single-shot OpenAI-compat call is a toy that fails on real models:

      - `think=False`: thinking-capable models (deepseek-r1, qwen3, kimi, gpt-oss, most cloud
        reasoning models) otherwise route their whole output budget into a hidden `thinking` field
        and return EMPTY `content`. Without this every reasoning model is silently broken.
      - explicit `num_ctx`: Ollama defaults the context window to **2048** regardless of the model's
        real capacity, so a long input (a growing conversation transcript) is truncated to its tail
        and the model parrots the last turn. Set it to the model's actual window.
      - retry with backoff: a daemon hiccup or a cloud-tier 503 must not crash a whole run.

    Native `/api/chat` (not the OpenAI-compat `/v1`) because that endpoint is where `num_ctx` and
    `think` live. httpx is imported lazily (the `openai-compat` extra), so importing this module
    never requires httpx in CI. temperature defaults to 0 for as-reproducible-as-a-real-model-gets
    walkthroughs. Local Ollama needs no auth; set `api_key` for direct api.ollama.com cloud access
    (local `:cloud` tags route through the daemon with no key once `ollama signin` has run)."""

    def __init__(
        self,
        model: str,
        *,
        base_url: str = "http://localhost:11434",
        api_key: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 512,
        num_ctx: int = 32768,
        think: bool = False,
        timeout: float = 120.0,
        max_retries: int = 3,
        system: str | None = None,
    ) -> None:
        # tolerate a trailing `/v1` from the old OpenAI-compat default so existing call sites keep
        # working; the native chat route is `<base>/api/chat`.
        base = base_url.rstrip("/")
        if base.endswith("/v1"):
            base = base[:-3]
        self._endpoint = f"{base}/api/chat"
        self._model = model
        self._api_key = api_key
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._num_ctx = num_ctx
        self._think = think
        self._timeout = timeout
        self._max_retries = max_retries
        self._system = system

    def _request(self, prompt: str) -> tuple[dict[str, str], dict[str, object]]:
        messages: list[dict[str, str]] = []
        if self._system:
            messages.append({"role": "system", "content": self._system})
        messages.append({"role": "user", "content": prompt})
        options: dict[str, object] = {"num_ctx": self._num_ctx, "temperature": self._temperature}
        if self._max_tokens > 0:
            options["num_predict"] = self._max_tokens
        payload: dict[str, object] = {
            "model": self._model,
            "messages": messages,
            "stream": False,
            "think": self._think,  # force useful output into `content`, not a hidden thinking field
            "options": options,
        }
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers, payload

    @staticmethod
    def _content(data: dict[str, object]) -> str:
        message = data.get("message")
        text = message.get("content", "") if isinstance(message, dict) else ""
        return str(text).strip()

    @staticmethod
    def _usage(data: dict[str, object], model: str) -> ModelUsage:
        """Read Ollama's native /api/chat accounting off the response — the fields `_content` used to
        discard. prompt_eval_count = prompt tokens, eval_count = generated tokens. wall_ms is the
        INFERENCE latency (prompt_eval_duration + eval_duration, ns -> ms) — NOT total_duration, which
        folds in load_duration (seconds of VRAM load on a cold call) and would confound a
        latency comparison by cache state. Falls back to total_duration only if the
        eval phases are absent. Missing or odd-typed fields degrade to 0, never raise."""

        def _i(key: str) -> int:
            v = data.get(key)
            return int(v) if isinstance(v, (int, float)) else 0

        eval_ns = _i("prompt_eval_duration") + _i("eval_duration")
        wall_ns = eval_ns if eval_ns > 0 else _i("total_duration")
        return ModelUsage(
            model=model,
            prompt_tokens=_i("prompt_eval_count"),
            completion_tokens=_i("eval_count"),
            wall_ms=wall_ns // 1_000_000,
            estimated=False,  # provider truth
        )

    def _chat(self, prompt: str) -> dict[str, object]:
        """One POST to /api/chat with retry+backoff, returning the parsed response dict. The shared
        core of `respond` / `respond_metered`, so the retry discipline lives in exactly one place."""
        import time

        import httpx  # lazy: the openai-compat optional extra; kernel/CI need not have it

        headers, payload = self._request(prompt)
        last_exc: Exception | None = None
        for attempt in range(self._max_retries):
            try:
                resp = httpx.post(
                    self._endpoint, headers=headers, json=payload, timeout=self._timeout
                )
                resp.raise_for_status()
                data: dict[str, object] = resp.json()
                return data
            except (
                httpx.HTTPError
            ) as exc:  # transport OR 4xx/5xx: retry with backoff, then fail loud
                last_exc = exc
                if attempt < self._max_retries - 1:
                    time.sleep(1.0 * (2**attempt))
        raise RuntimeError(
            f"OllamaResponder({self._model}) failed after {self._max_retries} attempts: {last_exc!r}"
        )

    async def _achat(self, prompt: str) -> dict[str, object]:
        """Async sibling of `_chat` over httpx.AsyncClient — the await is genuinely CANCELLABLE, so a
        cancelled Producer (cancel-others / a finalise racing an in-flight call) cancels the request
        rather than orphaning a worker thread inside a blocking POST (the shutdown-stall fix: a
        blocking call wrapped in asyncio.to_thread cannot be cancelled, so asyncio.run then blocks on
        the default executor up to `timeout`)."""
        import asyncio as _asyncio

        import httpx

        headers, payload = self._request(prompt)
        last_exc: Exception | None = None
        for attempt in range(self._max_retries):
            try:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    resp = await client.post(self._endpoint, headers=headers, json=payload)
                resp.raise_for_status()
                data: dict[str, object] = resp.json()
                return data
            except httpx.HTTPError as exc:
                last_exc = exc
                if attempt < self._max_retries - 1:
                    await _asyncio.sleep(1.0 * (2**attempt))
        raise RuntimeError(
            f"OllamaResponder({self._model}) failed after {self._max_retries} attempts: {last_exc!r}"
        )

    def respond(self, prompt: str) -> str:
        """Synchronous call (the Responder protocol + non-async callers). For use INSIDE an async
        Producer, prefer `call_responder`, which routes through `arespond` so the call is cancellable
        rather than orphaning a worker thread on cancel-others / finalise."""
        return self._content(self._chat(prompt))

    def respond_metered(self, prompt: str) -> tuple[str, ModelUsage]:
        """`respond`, plus the provider's own token/latency accounting as a ModelUsage — the
        measurement that `_content` alone throws away."""
        data = self._chat(prompt)
        return self._content(data), self._usage(data, self._model)

    async def arespond(self, prompt: str) -> str:
        """Async, cancellable call (see `_achat`) — the path `call_responder` prefers."""
        return self._content(await self._achat(prompt))

    async def arespond_metered(self, prompt: str) -> tuple[str, ModelUsage]:
        """Async sibling of `respond_metered`: the cancellable call plus ModelUsage accounting."""
        data = await self._achat(prompt)
        return self._content(data), self._usage(data, self._model)


async def call_responder(responder: Responder, prompt: str) -> str:
    """Invoke a Responder from inside an async Producer WITHOUT blocking the event loop.

    A real responder (OllamaResponder, any network/IO-backed model) does blocking I/O. Calling it
    directly serializes every Producer on the single event loop — so the substrate's headline
    property (N candidates streaming concurrently; "wall-clock latency drops because nothing is
    sequential that doesn't have to be") is NOT realized on the real-model path: the candidates run
    one after another. Offload the blocking call to a worker thread so the loop stays free and the
    Producers genuinely overlap.

    A responder that exposes an async `arespond` (OllamaResponder does) is awaited DIRECTLY — real
    network I/O over httpx.AsyncClient, genuinely cancellable, so a cancelled Producer cancels the
    request rather than orphaning a worker thread (which `asyncio.to_thread` cannot cancel, stalling
    process shutdown up to the responder timeout — REVIEW.md kernel-correctness-1).

    DeterministicResponder is pure CPU and instant; it is called SYNCHRONOUSLY here (no thread, and
    this coroutine then completes without awaiting, so it never yields control). That is deliberate:
    in CI the deterministic stand-ins must complete in a fixed order so concurrent Producers produce
    a byte-identical record (N-DET-1 / conformance check 9). A blocking custom responder (pure-code
    transform, etc.) still offloads to a thread for concurrency. So: async real responders are
    cancellable; stand-ins stay sync (determinism); other blocking responders offload.
    """
    arespond = getattr(responder, "arespond", None)
    if callable(arespond):
        return str(await arespond(prompt))
    if isinstance(responder, DeterministicResponder):
        return responder.respond(prompt)
    return await asyncio.to_thread(responder.respond, prompt)


async def call_responder_metered(responder: Responder, prompt: str) -> tuple[str, ModelUsage]:
    """Like `call_responder`, but also returns a `ModelUsage` for the call — emit it from the Producer
    so the inner record carries per-call token/latency accounting.

    A responder exposing `arespond_metered` (OllamaResponder) returns the provider's REAL counts. Any
    other responder (the DeterministicResponder stand-in, a custom seam) has no native accounting, so
    usage is DERIVED deterministically — word-count token estimates and wall_ms=0: stable enough to
    keep a CI record byte-identical, and honest that it is an estimate, not provider truth (the model
    field carries the responder's identity so a reader can tell the two apart). The text is obtained
    through the same `call_responder` path, preserving its concurrency/cancellation discipline."""
    ametered = getattr(responder, "arespond_metered", None)
    if callable(ametered):
        text, usage = await ametered(prompt)
        return str(text), usage
    text = await call_responder(responder, prompt)
    model = str(getattr(responder, "_model", type(responder).__name__))
    usage = ModelUsage(
        model=model,
        prompt_tokens=len(prompt.split()),
        completion_tokens=len(text.split()),
        wall_ms=0,
        estimated=True,  # word-count stand-in, NOT provider truth — marked in the data
    )
    return text, usage
