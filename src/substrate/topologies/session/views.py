"""Session-topology Views (piece A, sprint 205).

`model_failures` filters the reserved `substrate.ProducerFailed` stream down to the
model producer alone — the `park-on-model-error` trigger (sprint 206) reads it to fire
`Park{reason: "model_error"}`. Mirrors the pattern in `kernel/views.py::StartedCompletedCounts`,
which inspects the same `producer.kind` field on the same reserved lifecycle events.
"""

from __future__ import annotations

from typing import Any

from ...types import Event, Subscription

_PRODUCER_FAILED = "substrate.ProducerFailed"


class ModelFailures:
    """Payloads of `substrate.ProducerFailed` where `producer.kind == "model"`.

    Every other `ProducerFailed` (tool, park, session_end, any future producer) is dropped
    at update time. `value()` returns the accumulated list of matching payloads, ordered
    by emit. Deterministic (payload-derived, no wall-clock read).
    """

    deterministic = True

    def __init__(self) -> None:
        self.subscription = Subscription(kinds=frozenset({_PRODUCER_FAILED}))
        self._items: list[Any] = []

    def update(self, event: Event) -> None:
        payload = event.payload if isinstance(event.payload, dict) else {}
        ref = payload.get("producer")
        kind = ref.get("kind") if isinstance(ref, dict) else None
        if kind == "model":
            self._items.append(payload)

    def value(self) -> list[Any]:
        return list(self._items)
