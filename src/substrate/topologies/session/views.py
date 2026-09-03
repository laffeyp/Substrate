# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Session-topology Views (piece A, sprint 205).

`model_failures` filters the reserved `substrate.ProducerFailed` stream down to the
model producer alone — the `park-on-model-error` trigger (sprint 206) reads it to fire
`Park{reason: "model_error"}`. Mirrors the pattern in `kernel/views.py::StartedCompletedCounts`,
which inspects the same `producer.kind` field on the same reserved lifecycle events.

`FragmentCohort` owns turn-scoping for the prompt composer. Session-open
fragments (role, bundle_*, tools_suite, parent_context) fire once at
RunStarted and land in every turn's PromptComposed. Turn-scoped fragments
(per_turn, user_message) fire on the per-turn chain and belong only to
their turn's PromptComposed. FragmentCohort tracks both classes and
clears the turn slice on every PromptComposed emission, so turn N's
composed prompt cannot carry turn N-1's user message.
"""

from __future__ import annotations

from typing import Any

from ...constants import PRODUCER_FAILED
from ...types import Event, Subscription
from .vocabulary import (
    PROMPT_COMPOSED,
    PROMPT_FRAGMENT,
    SESSION_OPEN_SOURCES,
    TURN_SCOPED_SOURCES,
    PromptSource,
)

_PRODUCER_FAILED = PRODUCER_FAILED


def producer_kind_from_lifecycle_payload(payload: Any) -> str | None:
    """Read `producer.kind` off a `substrate.ProducerStarted / Failed / Cancelled` payload.

    The lifecycle envelopes carry `payload["producer"]` as `{kind, instance, parent}` per
    kernel §4. Trigger predicates and the ModelFailures view both need to filter by that
    kind; this helper is the one source of truth for the defensive `isinstance` ladder.
    """
    ref = payload.get("producer") if isinstance(payload, dict) else None
    return ref.get("kind") if isinstance(ref, dict) else None


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
        if producer_kind_from_lifecycle_payload(payload) == "model":
            self._items.append(payload)

    def value(self) -> list[Any]:
        return list(self._items)


class FragmentCohort:
    """Turn-scoped view over `PromptFragment` events.

    Two internal buckets. `_session_open: dict[PromptSource, tuple[int, dict]]`
    keeps one slot per session-open source; the latest (seq, payload) wins so a
    re-emission overwrites cleanly rather than stacking. `_turn: list[tuple[int, dict]]`
    accumulates per-turn fragments (per_turn, user_message) in arrival order and
    clears on every `PromptComposed` — the composer's own emission is the turn
    boundary signal, so the next turn's cohort starts empty.

    `value()` returns a merged list of `(seq, payload)` tuples ordered by seq.
    The composer's input builder splits each tuple into `fragments` and
    `fragment_seqs` so PromptComposed carries real record seqs, not positional
    indices — a reader can trace back from a composed event to every source
    PromptFragment envelope by seq.

    An unknown source value is dropped with no state change. Deterministic
    (payload-derived, no wall-clock read); the compose-emit boundary is a
    typed record event, not an external timer.
    """

    deterministic = True

    def __init__(self) -> None:
        self.subscription = Subscription(kinds=frozenset({PROMPT_FRAGMENT, PROMPT_COMPOSED}))
        self._session_open: dict[PromptSource, tuple[int, dict[str, Any]]] = {}
        self._turn: list[tuple[int, dict[str, Any]]] = []

    def update(self, event: Event) -> None:
        payload = event.payload if isinstance(event.payload, dict) else {}
        if event.kind == PROMPT_COMPOSED:
            self._turn.clear()
            return
        raw_source = payload.get("source")
        if not isinstance(raw_source, str):
            return
        try:
            source = PromptSource(raw_source)
        except ValueError:
            return
        entry = (event.seq, dict(payload))
        if source in SESSION_OPEN_SOURCES:
            self._session_open[source] = entry
        elif source in TURN_SCOPED_SOURCES:
            self._turn.append(entry)

    def value(self) -> list[tuple[int, dict[str, Any]]]:
        merged = list(self._session_open.values()) + list(self._turn)
        merged.sort(key=lambda item: item[0])
        return merged
