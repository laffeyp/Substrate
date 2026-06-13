"""Standard Views — deterministic incremental projections over the bus (F-VIEW-2).

Each declares a Subscription; the writer's subscription index consults a View only on
matching events, and calls `update` synchronously in append-cycle step 3 (before any
Route or Predicate). `deterministic` declares participation in N-DET-1.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import Any

from .types import Event, Subscription


class BufferView:
    """Accumulated payloads from one Producer kind (kernel §4 — the most common View)."""

    deterministic = True

    def __init__(self, producer: str) -> None:
        self.subscription = Subscription(producers=frozenset({producer}))
        self._items: list[Any] = []

    def update(self, event: Event) -> None:
        self._items.append(event.payload)

    def value(self) -> list[Any]:
        return list(self._items)


class KindCount:
    """Count of events of one kind."""

    deterministic = True

    def __init__(self, kind: str) -> None:
        self.subscription = Subscription(kinds=frozenset({kind}))
        self._n = 0

    def update(self, event: Event) -> None:
        self._n += 1

    def value(self) -> int:
        return self._n


class PerKindLatest:
    """Latest payload seen for one kind."""

    deterministic = True

    def __init__(self, kind: str) -> None:
        self.subscription = Subscription(kinds=frozenset({kind}))
        self._latest: Any = None

    def update(self, event: Event) -> None:
        self._latest = event.payload

    def value(self) -> Any:
        return self._latest


class StartedCompletedCounts:
    """Per-Producer-kind started vs ended (completed+failed+cancelled) counts — the
    substrate of the progress-gating / cohort-frontier predicate (kernel §"Progress
    gating"). Keys on the subject Producer identity carried in the lifecycle payload
    (P-SUBJECT-ID, ratified into vocabulary v0.1)."""

    deterministic = True

    def __init__(self) -> None:
        self.subscription = Subscription(
            kinds=frozenset(
                {
                    "substrate.ProducerStarted",
                    "substrate.ProducerCompleted",
                    "substrate.ProducerFailed",
                    "substrate.ProducerCancelled",
                }
            )
        )
        self._started: dict[str, int] = {}
        self._ended: dict[str, int] = {}

    def update(self, event: Event) -> None:
        payload = event.payload if isinstance(event.payload, dict) else {}
        ref = payload.get("producer")
        kind = ref.get("kind") if isinstance(ref, dict) else None
        if kind is None:
            return
        bucket = self._started if event.kind == "substrate.ProducerStarted" else self._ended
        bucket[kind] = bucket.get(kind, 0) + 1

    def value(self) -> Any:
        return MappingProxyType({"started": dict(self._started), "ended": dict(self._ended)})
