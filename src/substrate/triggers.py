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
    """Fires continuously while the predicate holds, throttled by a logical cooldown
    (append-count). Wall-clock cooldown handling lives in the runtime (it owns the
    clock + the replay-ceiling demotion)."""

    def __init__(self, cooldown: Cooldown | None = None) -> None:
        self.cooldown = cooldown or Logical(0)
        self._last_index: int | None = None

    def admit(self, event: Event, append_index: int) -> tuple[bool, Any]:
        if isinstance(self.cooldown, Logical) and self._last_index is not None:
            if append_index - self._last_index < self.cooldown.appends:
                return False, None
        self._last_index = append_index
        return True, None


FiringPolicy = Once | PerEvent | PerKey | WhileTrue
