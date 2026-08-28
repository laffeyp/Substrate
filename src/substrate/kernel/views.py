"""Standard Views — deterministic incremental projections over the bus (F-VIEW-2).

Each declares a Subscription; the writer's subscription index consults a View only on
matching events, and calls `update` synchronously in append-cycle step 3 (before any
Route or Predicate). `deterministic` declares participation in N-DET-1.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import Any

from ..constants import (
    PRODUCER_CANCELLED,
    PRODUCER_COMPLETED,
    PRODUCER_FAILED,
    PRODUCER_STARTED,
)
from ..types import Event, Subscription


class BufferView:
    """Accumulated payloads from one Producer kind (kernel §4 — the most common View).

    MEMORY (same class as PerKey's N-MEM-1): holds EVERY matching payload for the run's lifetime —
    unbounded for a high-volume kind — and `value()` returns an O(history) copy, so a Predicate
    that scans it each event is O(history)/event (→ quadratic over the run). For a long,
    high-volume kind use KindCount / PerKindLatest, or a bounded/windowed View, not a growing
    buffer. Negligible at small scale (tens–hundreds of items); a real cost only in the thousands.
    """

    deterministic = True

    def __init__(self, producer: str) -> None:
        self.subscription = Subscription(producers=frozenset({producer}))
        self._items: list[Any] = []

    def update(self, event: Event) -> None:
        self._items.append(event.payload)

    def value(self) -> list[Any]:
        return list(self._items)


class KindBuffer:
    """Accumulated payloads of one event KIND (a kind-subscribed sibling of BufferView, which
    subscribes by Producer kind). Useful when several Producer kinds emit the same event kind
    and a Predicate gates on the aggregate (e.g. R-1's "≥K Candidate answers" Bus-view).

    MEMORY: same unbounded-growth + O(history) `value()` caveat as BufferView (above) — use
    KindCount / PerKindLatest or a bounded View for a long, high-volume kind."""

    deterministic = True

    def __init__(self, kind: str) -> None:
        self.subscription = Subscription(kinds=frozenset({kind}))
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
                    PRODUCER_STARTED,
                    PRODUCER_COMPLETED,
                    PRODUCER_FAILED,
                    PRODUCER_CANCELLED,
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
        bucket = self._started if event.kind == PRODUCER_STARTED else self._ended
        bucket[kind] = bucket.get(kind, 0) + 1

    def value(self) -> Any:
        return MappingProxyType({"started": dict(self._started), "ended": dict(self._ended)})
