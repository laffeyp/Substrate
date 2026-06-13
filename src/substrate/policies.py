"""TerminationPolicy + the standard recipe set (kernel §8; F-TERM-1, F-LIFE-2).

A TerminationPolicy interprets the run state (the just-processed event, the
completion/failure counts, quiescence) into a Decision. The contract is the callback;
the recipes ship on top as named convenience functions (kernel §8). Per-Producer and
per-run scoping compose per the kernel; v0.1 ships the run-scoped recipes the
reference topologies need.
"""
from __future__ import annotations

import enum
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


class Decision(enum.Enum):
    CONTINUE = "continue"
    FINALISE_RUN = "finalise-run"
    CANCEL_OTHERS = "cancel-others"
    LET_FINISH = "let-finish"
    PAUSE_AWAIT_INPUT = "pause-await-input"


@dataclass(frozen=True)
class TermContext:
    """What a TerminationPolicy sees. `event` is the just-appended event (or None on a
    pure quiescence check). `counts(kind)` returns the run's count of that event kind."""

    event: Any
    quiescent: bool
    running: int
    started: int
    completed: int
    counts: Callable[[str], int]
    resume_condition: str | None = None


class TerminationPolicy:
    """A named decision callback. `name` is recorded in substrate.TerminationMatched."""

    def __init__(self, name: str, fn: Callable[[TermContext], Decision],
                 resume_condition: str | None = None) -> None:
        self.name = name
        self._fn = fn
        self.resume_condition = resume_condition

    def decide(self, ctx: TermContext) -> Decision:
        return self._fn(ctx)


def threshold_count(kind: str, n: int) -> TerminationPolicy:
    """Finalise once `n` events of `kind` have been appended."""
    return TerminationPolicy(
        f"threshold_count({kind},{n})",
        lambda c: Decision.FINALISE_RUN if c.counts(kind) >= n else Decision.CONTINUE,
    )


def all_completed() -> TerminationPolicy:
    """Finalise on quiescence once every started Producer has ended."""
    return TerminationPolicy(
        "all_completed",
        lambda c: Decision.FINALISE_RUN
        if (c.quiescent and c.running == 0 and c.started > 0 and c.completed >= c.started)
        else Decision.CONTINUE,
    )


def quiescence_with_watchdog(seconds: float = 30.0) -> TerminationPolicy:
    """Finalise when the run goes quiescent (no work in flight). `seconds` is the
    watchdog poll window the runtime uses to detect quiescence."""
    return TerminationPolicy(
        f"quiescence_with_watchdog({seconds})",
        lambda c: Decision.FINALISE_RUN if (c.quiescent and c.running == 0) else Decision.CONTINUE,
        resume_condition=None,
    )


def pause_await_input(when: Callable[[TermContext], bool], resume_condition: str) -> TerminationPolicy:
    """Pause and emit a typed resume_condition when `when` holds (kernel halt-with-resume)."""
    return TerminationPolicy(
        "pause_await_input",
        lambda c: Decision.PAUSE_AWAIT_INPUT if when(c) else Decision.CONTINUE,
        resume_condition=resume_condition,
    )


def any_of(*policies: TerminationPolicy) -> TerminationPolicy:
    """Finalise/pause when any composed policy returns a non-CONTINUE decision."""
    name = "any_of(" + ",".join(p.name for p in policies) + ")"

    def fn(ctx: TermContext) -> Decision:
        for p in policies:
            d = p.decide(ctx)
            if d is not Decision.CONTINUE:
                return d
        return Decision.CONTINUE

    return TerminationPolicy(name, fn)


def all_of(*policies: TerminationPolicy) -> TerminationPolicy:
    """Finalise only when all composed policies agree to finalise."""
    name = "all_of(" + ",".join(p.name for p in policies) + ")"

    def fn(ctx: TermContext) -> Decision:
        decisions = [p.decide(ctx) for p in policies]
        if decisions and all(d is Decision.FINALISE_RUN for d in decisions):
            return Decision.FINALISE_RUN
        return Decision.CONTINUE

    return TerminationPolicy(name, fn)
