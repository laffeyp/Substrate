"""Reference topologies R-1/R-2/R-3 (product §8) — acceptance tests, not product features.

Dual-mode: CI mode (deterministic stand-in Producers, gated every commit) proves the wiring;
walkthrough mode (real local LLMs via the openai-compat adapter) proves the claim each
topology exists to demonstrate. These are topology-layer code — they import only
`substrate.api` (like the CLI), never kernel internals.

The model-adapter seam is re-exported here (review #23): a topology that wants a custom LLM
backend implements `Responder` (`respond(prompt: str) -> str`) and hands it to the topology —
import it from `substrate.reference`, not the underscore `_models` module.
"""

from ._models import (
    CliResponder,
    DeterministicResponder,
    ModelUsage,
    OllamaResponder,
    Responder,
    call_responder,
    call_responder_metered,
)

__all__ = [
    "Responder",
    "DeterministicResponder",
    "OllamaResponder",
    "CliResponder",
    "call_responder",
    "ModelUsage",
    "call_responder_metered",
]
