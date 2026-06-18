"""Proper scoring rules for participant confidence claims (lifted from the precursor).

A conversation speaker that attaches a probability to a claim is making a forecast. Without a
payoff tied to calibration those numbers are *cheap talk* (Crawford & Sobel 1982): a rational
reader ignores them. A scoring rule fixes that — it is *proper* iff a calibrated reporter
minimises their expected loss by reporting their true belief (Brier 1950, Good 1952, Selten
1998). Score a speaker's round-N confidence claims against what round N+1 observed, accumulate
across the conversation, and suddenly calibration pays.

Three proper rules ship, lower-is-better and normalised so the measurement layer compares runs
without per-rule sign handling: Brier (quadratic, symmetric), LogLoss (penalises overconfident
errors sharply), Spherical (between the two). Adding a rule is one class + one registry entry.
Pure — no LLM, no I/O — so it is fully deterministic and unit-testable.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol, runtime_checkable


class ScoringError(Exception):
    """Invalid scoring input, or no rule registered under the requested name."""


@dataclass(frozen=True)
class Prediction:
    """A claim made with attached confidence — a probability in [0, 1] that the claim is true.
    `claim` is an opaque id (a short paraphrase); matching predictions to outcomes is the
    caller's job."""

    claim: str
    confidence: float

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ScoringError(f"confidence must be in [0, 1]; got {self.confidence!r}")


@dataclass(frozen=True)
class Outcome:
    """The realised value of a claim, graded after the fact, in [0, 1]: 0.0 false, 1.0 true,
    intermediate for partial materialisation."""

    claim: str
    value: float

    def __post_init__(self) -> None:
        if not 0.0 <= self.value <= 1.0:
            raise ScoringError(f"value must be in [0, 1]; got {self.value!r}")


@runtime_checkable
class ScoringRule(Protocol):
    """A proper scoring rule. Stateless; lower scores are better; perfect calibration scores 0.

    `name` is a read-only property in the Protocol so a frozen dataclass's `name` field satisfies
    it (a read-write Protocol data member would not match a frozen attribute under mypy --strict).
    """

    @property
    def name(self) -> str: ...

    def score(self, prediction: Prediction, outcome: Outcome) -> float: ...


@dataclass(frozen=True)
class BrierScore:
    """Quadratic (Brier 1950): (confidence - outcome)^2. Bounded [0, 1], symmetric; perfect → 0,
    perfectly wrong → 1."""

    name: str = "brier"

    def score(self, prediction: Prediction, outcome: Outcome) -> float:
        diff = prediction.confidence - outcome.value
        return diff * diff


@dataclass(frozen=True)
class LogLossScore:
    """Negative log-likelihood (Good 1952). Proper; penalises overconfident wrong forecasts
    sharply. Confidence is clamped to [eps, 1-eps] so one pathological claim cannot poison an
    aggregate."""

    name: str = "log_loss"
    epsilon: float = 1e-6

    def score(self, prediction: Prediction, outcome: Outcome) -> float:
        c = min(max(prediction.confidence, self.epsilon), 1.0 - self.epsilon)
        v = outcome.value
        return -(v * math.log(c) + (1.0 - v) * math.log(1.0 - c))


@dataclass(frozen=True)
class SphericalScore:
    """Spherical (Roby 1965, Selten 1998), returned as 1 - S so lower-is-better and calibrated →
    0. Less sensitive to overconfident wrong forecasts than log-loss, more discriminating
    between similar calibrations than Brier."""

    name: str = "spherical"

    def score(self, prediction: Prediction, outcome: Outcome) -> float:
        p = prediction.confidence
        v = outcome.value
        reward = (p * v + (1.0 - p) * (1.0 - v)) / math.sqrt(p * p + (1.0 - p) * (1.0 - p))
        return 1.0 - reward


REGISTRY: dict[str, Callable[[], ScoringRule]] = {
    "brier": BrierScore,
    "log_loss": LogLossScore,
    "spherical": SphericalScore,
}


def select_scoring_rule(name: str) -> ScoringRule:
    """Look up and instantiate a scoring rule by (case-insensitive) name; raises ScoringError
    for unknown names, naming the known rules."""
    key = name.strip().lower()
    if key not in REGISTRY:
        raise ScoringError(f"unknown scoring rule {name!r}; known: {sorted(REGISTRY)}")
    return REGISTRY[key]()
