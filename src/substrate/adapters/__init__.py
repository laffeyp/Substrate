"""substrate.adapters — the model / tool adapter layer (a peer of substrate.api).

Home for the concrete backends a topology's Producers call: the `Responder` implementations
(`DeterministicResponder` / `OllamaResponder`) and the async `call_responder` helpers. A peer of
`api`, deliberately NOT a submodule of the acceptance-test `reference` package where these used to
live — so a new adapter (a CLI-agent Responder, an MCP tool bridge) has a canonical home beside the
model ones instead of accreting under `reference/` or `cli.py`. The `Responder` protocol itself
lives in `substrate.protocols` and is public as `substrate.api.Responder`.

Back-compat: `substrate.reference` still re-exports these (the public surface substrate-ui consumes),
via a thin shim at `reference/_models.py`. New code should import from `substrate.adapters`.
"""

from __future__ import annotations

from .ensemble import EnsembleResponder
from .models import (
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
    "EnsembleResponder",
    "ModelUsage",
    "call_responder",
    "call_responder_metered",
]
