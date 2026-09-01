# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Firing policies and cooldowns (kernel §6; technical §10).

A firing policy decides, given a satisfying event, whether the Trigger fires now and
under what `firing_key`. PerKey extraction is canonically encoded before dedup so
behavior is implementation-stable (technical §10). Cooldowns are logical by default
(append-counted); wall-clock is opt-in and demotes the replay ceiling to 3(b).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from msgspec import Struct

from ..encoding import canonical_bytes
from ..types import Event


# ── cooldowns ──────────────────────────────────────────────────────────────────
class Logical(Struct, frozen=True):
    """Cooldown counted in append cycles (deterministic, replayable)."""

    appends: int = 0


class WallClock(Struct, frozen=True):
    """Cooldown in seconds. Opt-in; flagged at registration; demotes replay to 3(b)."""

    seconds: float = 1.0


Cooldown = Logical | WallClock


# ── firing policies ──────────────────────────────────────────────────────────--
class Once:
    """First satisfaction fires; further satisfactions ignored."""

    def __init__(self) -> None:
        self._fired = False

    def admit(self, event: Event, append_index: int) -> tuple[bool, Any]:
        if self._fired:
            return False, None
        self._fired = True
        return True, None


class PerEvent:
    """Each newly-satisfying event fires the Trigger once."""

    def admit(self, event: Event, append_index: int) -> tuple[bool, Any]:
        return True, None


class PerKey:
    """One firing per distinct key extracted from the event (CEP window-and-key).

    N-MEM-1 (memory bound — documented behavior, v1.0): `_seen` grows by one canonical-key
    entry per DISTINCT key the Trigger ever fires on, for the lifetime of the run. It is NOT
    evicted. For a bounded-key topology (e.g. PerKey over a fixed set of categories) this is
    O(distinct keys) and fine. For an UNBOUNDED-key, long-running topology (e.g. PerKey over a
    per-message id that never repeats) `_seen` grows without bound — the dedup set is the cost
    of the "fire exactly once per key, forever" guarantee. v1.0 does NOT bound it: a windowed
    / LRU eviction would silently let an evicted key RE-FIRE (a dedup-correctness change, not a
    free optimization), so it needs a decision (a key-window/TTL on PerKey) rather than a quiet
    cap. The operational guidance for v1.0: do not key PerKey on an unbounded-cardinality field
    in a long-lived run; use PerEvent (no dedup state) or a bounded key. (Route `staged` is
    bounded by construction — keyed by the static set of declared Route slots, latest-wins per
    slot — so it is NOT part of this growth; only `_seen` is.)"""

    def __init__(self, fn: Callable[[Event], Any]) -> None:
        self._fn = fn
        self._seen: set[bytes] = set()

    def admit(self, event: Event, append_index: int) -> tuple[bool, Any]:
        key = self._fn(event)
        canonical = canonical_bytes(key)  # implementation-stable dedup (§10)
        if canonical in self._seen:
            return False, None
        self._seen.add(canonical)
        return True, key


class WhileTrue:
    """Fires continuously while the predicate holds, throttled by a cooldown.

    The cooldown is a TRIGGER-level concept (kernel §6 — "throttled by a cooldown"):
    cooldown enforcement lives in the runtime, which owns the single, replayable
    append-counter (subscription-matched cycles) and the wall-clock clock + replay-ceiling
    demotion. WhileTrue therefore does NOT self-throttle (that would double-enforce);
    `cooldown` is exposed so TopologyBuilder.trigger can lift it to the trigger level."""

    def __init__(self, cooldown: Cooldown | None = None) -> None:
        self.cooldown = cooldown or Logical(0)

    def admit(self, event: Event, append_index: int) -> tuple[bool, Any]:
        # The predicate already gated this call; firing is admitted. The cooldown is
        # applied by the runtime (a single enforcement point), not here.
        return True, None


# CLOSED kernel set (review #23): firing policies — and Cooldowns above — are kernel-defined
# semantics, NOT an open extension point. A topology author SELECTS one of these; they cannot add
# a custom firing policy (the union is closed; mypy rejects anything outside it). This is by design
# (firing semantics are part of the replay contract) and is stated here so an author doesn't try —
# unlike Views and TerminationPolicies, which ARE open (constructible Protocols / callbacks).
FiringPolicy = Once | PerEvent | PerKey | WhileTrue
