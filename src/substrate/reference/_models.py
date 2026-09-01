# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Back-compat re-exports — the model-adapter seam moved to `substrate.adapters` (a peer of `api`).

The concrete Responders (`DeterministicResponder` / `OllamaResponder`), the `ModelUsage` event, and
the `call_responder` helpers now live in `substrate.adapters` (see its docstring for why the seam
was a mis-file under the acceptance-test `reference` package). This module re-exports them so every
existing import keeps working unchanged: the public `from substrate.reference import ...` surface
(consumed by substrate-ui) and the topologies'/assay's `from ...reference._models import ...`.

New code should import from `substrate.adapters`.
"""

from __future__ import annotations

from ..adapters.models import (
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
    "ModelUsage",
    "call_responder",
    "call_responder_metered",
]
