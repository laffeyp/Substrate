"""The dual-mode model seam for the reference topologies (product §8).

Every reference topology is dual-mode: a CI mode with DETERMINISTIC stand-in Producers
(proves the wiring, runs every commit, no network) and a WALKTHROUGH mode with real local
LLMs (proves the claim — adjudication in R-1, overlap in R-3). The seam is a `Responder`:
`respond(prompt) -> str`. Topologies are written against the Responder, not against any
model; the mode is chosen by which Responder the run is handed.

  - DeterministicResponder — canned, seed-derived answers; pure, no I/O. The CI mode. The
    spec is explicit that CI mode alone "sanitizes away the thing each topology exists to
    demonstrate", so CI mode proves WIRING only and never masquerades as the demonstration.
  - OllamaResponder — a real call to an OpenAI-compatible chat endpoint (Ollama at
    http://localhost:11434/v1 by default) over httpx (the `openai-compat` optional extra;
    the kernel imports none of it — httpx is imported lazily here). The WALKTHROUGH mode.

Local models only: the walkthrough uses llama3.2:1b (weak ensemble members / quick runs)
and huihui_ai/qwen2.5-coder-abliterate:7b (R-1 adjudicator / R-3 writer); cloud models are
avoided (the demonstration runs on the Architect's machine).
"""

from __future__ import annotations

import hashlib

# The Responder Protocol now lives among the structural protocols (substrate.protocols) and is
# public as substrate.api.Responder; re-exported here so `from substrate.reference import
# Responder` and the topologies' `from ..reference._models import Responder` keep working.
from ..protocols import Responder

__all__ = ["Responder", "DeterministicResponder", "OllamaResponder"]


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
    """A real local-LLM responder over an OpenAI-compatible chat endpoint (walkthrough mode).

    Defaults to Ollama at http://localhost:11434/v1 with the api key "ollama". httpx is
    imported lazily (the `openai-compat` extra), so importing this module never requires httpx
    in CI. temperature defaults to 0 for as-reproducible-as-a-real-model-gets walkthroughs;
    max_tokens is kept small (demonstration on the Architect's machine, not a benchmark)."""

    def __init__(
        self,
        model: str,
        *,
        base_url: str = "http://localhost:11434/v1",
        api_key: str = "ollama",
        temperature: float = 0.0,
        max_tokens: int = 256,
        timeout: float = 120.0,
        system: str | None = None,
    ) -> None:
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._timeout = timeout
        self._system = system

    def respond(self, prompt: str) -> str:
        import httpx  # lazy: the openai-compat optional extra; kernel/CI need not have it

        messages = []
        if self._system:
            messages.append({"role": "system", "content": self._system})
        messages.append({"role": "user", "content": prompt})
        resp = httpx.post(
            f"{self._base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self._api_key}"},
            json={
                "model": self._model,
                "messages": messages,
                "temperature": self._temperature,
                "max_tokens": self._max_tokens,
            },
            timeout=self._timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        return str(data["choices"][0]["message"]["content"]).strip()
