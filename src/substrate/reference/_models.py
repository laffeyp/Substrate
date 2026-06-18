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

# The Responder Protocol now lives among the structural protocols (substrate.protocols) and is
# public as substrate.api.Responder; re-exported here so `from substrate.reference import
# Responder` and the topologies' `from ..reference._models import Responder` keep working.
from ..protocols import Responder

__all__ = ["Responder", "DeterministicResponder", "OllamaResponder", "call_responder"]


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

    def respond(self, prompt: str) -> str:
        import time

        import httpx  # lazy: the openai-compat optional extra; kernel/CI need not have it

        messages: list[dict[str, str]] = []
        if self._system:
            messages.append({"role": "system", "content": self._system})
        messages.append({"role": "user", "content": prompt})
        options: dict[str, object] = {"num_ctx": self._num_ctx, "temperature": self._temperature}
        if self._max_tokens > 0:
            options["num_predict"] = self._max_tokens
        payload = {
            "model": self._model,
            "messages": messages,
            "stream": False,
            "think": self._think,  # force useful output into `content`, not a hidden thinking field
            "options": options,
        }
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        last_exc: Exception | None = None
        for attempt in range(self._max_retries):
            try:
                resp = httpx.post(self._endpoint, headers=headers, json=payload, timeout=self._timeout)
                resp.raise_for_status()
                data = resp.json()
                return str((data.get("message") or {}).get("content", "")).strip()
            except httpx.HTTPError as exc:  # transport OR 4xx/5xx: retry with backoff, then fail loud
                last_exc = exc
                if attempt < self._max_retries - 1:
                    time.sleep(1.0 * (2**attempt))
        raise RuntimeError(
            f"OllamaResponder({self._model}) failed after {self._max_retries} attempts: {last_exc!r}"
        )


async def call_responder(responder: Responder, prompt: str) -> str:
    """Invoke a Responder from inside an async Producer WITHOUT blocking the event loop.

    A real responder (OllamaResponder, any network/IO-backed model) does blocking I/O. Calling it
    directly serializes every Producer on the single event loop — so the substrate's headline
    property (N candidates streaming concurrently; "wall-clock latency drops because nothing is
    sequential that doesn't have to be") is NOT realized on the real-model path: the candidates run
    one after another. Offload the blocking call to a worker thread so the loop stays free and the
    Producers genuinely overlap.

    DeterministicResponder is pure CPU and instant; it is called SYNCHRONOUSLY here (no thread, and
    this coroutine then completes without awaiting, so it never yields control). That is deliberate:
    in CI the deterministic stand-ins must complete in a fixed order so concurrent Producers produce
    a byte-identical record (N-DET-1 / conformance check 9). Offloading them to threads would inject
    real scheduling nondeterminism into CI and make the committed records non-reproducible — exactly
    what must not happen. So: real responders offload (concurrency); stand-ins stay sync (determinism).
    """
    if isinstance(responder, DeterministicResponder):
        return responder.respond(prompt)
    return await asyncio.to_thread(responder.respond, prompt)
