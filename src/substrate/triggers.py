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

from .encoding import canonical_bytes
from .types import Event


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
    """One firing per distinct key extracted from the event (CEP window-and-key)."""

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


FiringPolicy = Once | PerEvent | PerKey | WhileTrue
