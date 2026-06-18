"""Grader instrument — score a speaker's prior confidence claims against the next turn.

The third instrument lifted from the precursor, and the one that closes the cheap-talk loop
with the scoring rules in `scoring.py`: a side Producer fired on each Turn reads the prior
turns and emits a typed Grade{claim, prior_confidence, observed_outcome} — did the prior
speaker's calibrated claim survive the turn that followed? A proper scoring rule (Brier /
log-loss / spherical) then converts the Grades to per-claim losses, so a speaker is PAID for
calibration, not for confident-sounding. Non-load-bearing (soft-fail).

In walkthrough mode the Producer is an LLM judging the claim; in CI it derives a stable
(confidence, outcome) from the transcript so the wiring runs deterministically.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from typing import Any

from msgspec import Struct

from ...reference._models import Responder
from .scoring import Outcome, Prediction, ScoringRule

_Factory = Callable[[], Any]


class Grade(Struct, frozen=True):
    """One graded claim: the prior speaker's claim id, the confidence they attached, and the
    observed outcome in [0, 1] (1 confirmed, 0 refuted, 0.5 unresolved)."""

    claim: str
    prior_confidence: float
    observed_outcome: float
    round: int


def grader_factory(responder: Responder) -> _Factory:
    async def grade(inp: Any) -> AsyncIterator[Grade]:
        rnd = int(inp.get("round", 0)) if hasattr(inp, "get") else 0
        prior = inp.get("prior_turns", []) if hasattr(inp, "get") else []
        if not prior:
            return  # nothing to grade before the first turn
        _ = responder.respond("grade the prior speaker's confidence claims")
        last = prior[-1]
        # CI: a deterministic pseudo-grade derived from the prior turn's text (a real grader is an
        # LLM judging the claim against the new turn; the scoring is identical either way).
        h = sum(str(last["text"]).encode())
        confidence = ((h % 90) + 5) / 100.0  # 0.05 .. 0.95
        outcome = float((h >> 1) & 1)  # 0.0 or 1.0
        yield Grade(
            claim=f"S{last['speaker']}-r{last['round']}",
            prior_confidence=confidence,
            observed_outcome=outcome,
            round=rnd,
        )

    return lambda: grade


def score_grades(grades: list[dict[str, Any]], rule: ScoringRule) -> dict[str, float]:
    """Aggregate Grade-event payloads into a per-claim loss under a proper scoring rule. Pure —
    the durable Grade events on the bus are the input; this computes the payoff from them."""
    losses: dict[str, float] = {}
    for g in grades:
        pred = Prediction(claim=str(g["claim"]), confidence=float(g["prior_confidence"]))
        out = Outcome(claim=str(g["claim"]), value=float(g["observed_outcome"]))
        losses[pred.claim] = rule.score(pred, out)
    return losses
