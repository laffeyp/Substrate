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
    """A named decision callback. `name` is recorded in substrate.TerminationMatched.

    `watchdog_seconds`, when set, is the writer's idle-poll window (how often the
    writer wakes to test quiescence when the inbox is idle) — set by
    quiescence_with_watchdog(seconds=). None means "use the runtime default poll".

    `finalisation`, when set, is a callable run at finalise-run time that produces the
    run's final output payload; it is recorded in substrate.RunFinalised.finalisation_payload
    and surfaced on RunResult.finalisation_payload. None → no payload (an empty RunFinalised).
    The payload must be canonical (§4.2); a non-canonical payload is dropped to None with the
    failure noted, never crashing finalisation."""

    def __init__(
        self,
        name: str,
        fn: Callable[[TermContext], Decision],
        resume_condition: str | None = None,
        watchdog_seconds: float | None = None,
        finalisation: Callable[[TermContext], Any] | None = None,
    ) -> None:
        self.name = name
        self._fn = fn
        self.resume_condition = resume_condition
        self.watchdog_seconds = watchdog_seconds
        self.finalisation = finalisation

    def decide(self, ctx: TermContext) -> Decision:
        return self._fn(ctx)

    def finalisation_payload(self, ctx: TermContext) -> Any | None:
        """The run's final output payload at finalise time, or None if the policy declares
        none. Exceptions propagate to the caller (which records the failure, not silently)."""
        return self.finalisation(ctx) if self.finalisation is not None else None


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
        lambda c: (
            Decision.FINALISE_RUN
            if (c.quiescent and c.running == 0 and c.started > 0 and c.completed >= c.started)
            else Decision.CONTINUE
        ),
    )


def cancel_all_others(when: Callable[[TermContext], bool]) -> TerminationPolicy:
    """Cancel every OTHER running Producer (all but the subject — the producer of the
    just-appended event) when `when(ctx)` holds (kernel §8; F-LIFE-2). CANCEL_OTHERS does NOT
    finalise: the cancelled Producers emit substrate.ProducerCancelled on the log and the run
    continues (typically to quiescence). The canonical R-1 use: fire on the adjudicator's
    completion, cancel the still-running candidates, then a quiescence/all-completed policy
    finalises. Compose: any_of(cancel_all_others(adjudicated), all_completed())."""
    return TerminationPolicy(
        "cancel_all_others",
        lambda c: Decision.CANCEL_OTHERS if when(c) else Decision.CONTINUE,
    )


def let_finish(when: Callable[[TermContext], bool]) -> TerminationPolicy:
    """Let all running Producers finish (no cancellation), then finalise — when `when(ctx)`
    holds (kernel §8; F-LIFE-2). LET_FINISH stops admitting new work and finalises once the
    in-flight Producers drain; here modelled as: when `when` holds AND the run is quiescent
    with all started Producers ended, finalise (the 'graceful drain' terminal)."""
    return TerminationPolicy(
        "let_finish",
        lambda c: (
            Decision.FINALISE_RUN
            if (when(c) and c.quiescent and c.running == 0)
            else Decision.CONTINUE
        ),
    )


def quiescence_with_watchdog(seconds: float = 30.0) -> TerminationPolicy:
    """Finalise when the run goes quiescent (no work in flight). `seconds` is the
    watchdog window the runtime uses to wake and test quiescence (it bounds the writer
    idle-poll interval; see Runtime._poll_s)."""
    return TerminationPolicy(
        f"quiescence_with_watchdog({seconds})",
        lambda c: Decision.FINALISE_RUN if (c.quiescent and c.running == 0) else Decision.CONTINUE,
        resume_condition=None,
        watchdog_seconds=seconds,
    )


def pause_await_input(
    when: Callable[[TermContext], bool], resume_condition: str
) -> TerminationPolicy:
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
