"""Structural protocols for the two user-implemented primitives: Producer and View.

These are typing.Protocol so user code satisfies them by shape, not inheritance
(design spec §9.6: factory returns a callable; no class hierarchy required). Signatures
mirror technical spec §16.
"""
from __future__ import annotations

from collections.abc import AsyncIterable
from typing import Any, Protocol, runtime_checkable

from .types import Event, Subscription


@runtime_checkable
class Producer(Protocol):
    """Anything implementing `start(input) -> AsyncIterable[Event]` (kernel §1).

    The runtime calls `start` with the sealed, resolved input and consumes the event
    stream until the Producer completes, fails, or is cancelled — emitting the
    corresponding lifecycle event. A Producer has no runtime-level identity, planning,
    or goal state (kernel non-goals); state lives on the log.
    """

    def start(self, input: Any) -> AsyncIterable[Event]: ...


@runtime_checkable
class View(Protocol):
    """A deterministic incremental projection over the bus (kernel §4).

    Updated synchronously in append-cycle step 3, before any Route or Predicate.
    `deterministic` declares whether `value()` is composed of RFC-8785-encodable
    types and so participates in N-DET-1 (byte-identical replay); a View holding
    non-canonical types sets it False and is flagged `determinism: excluded` at
    registration (technical §4.2).
    """

    subscription: Subscription
    deterministic: bool

    def update(self, event: Event) -> None: ...
    def value(self) -> Any: ...
