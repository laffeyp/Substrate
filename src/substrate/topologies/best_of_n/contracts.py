"""The shared best-of-N + correction record contract — the loop's vocabulary, in its CANONICAL home.

Moved here from coding_flow (review #61): the shared/lower loop module must not import its records from a
specific/higher consumer — that is a layering inversion and becomes a circular import the moment
coding_flow migrates onto best_of_n (the #43 refactor). Now the dependency flows one way: best_of_n owns
the contract; coding_flow, the swebench Repairer, and code_evolution all import it from here.

Registered in `process/WORKING_AGREEMENT.md` (#22). Frozen Structs; the bus boundary validates them.
"""

from __future__ import annotations

from msgspec import Struct


class Draft(Struct, frozen=True):
    """A request to draft a candidate. `context` is "" for the seed round, or the prior round's
    deterministic failures for a correction round."""

    round: int
    slot: int
    context: str


class Candidate(Struct, frozen=True):
    """A drafter's output — the raw model text the validator parses (coding_flow: `# path:`-headed files;
    swebench: SEARCH/REPLACE blocks)."""

    round: int
    slot: int
    response: str


class Verdict(Struct, frozen=True):
    """The validator's DETERMINISTIC verdict on one candidate. `passed` is the truth (gate exit code /
    applied-cleanly); `summary` the normalized log / structured reject reason fed back on correction."""

    round: int
    slot: int
    passed: bool
    returncode: int
    summary: str


class Solved(Struct, frozen=True):
    """A passing candidate was selected — the loop's success terminal (an internal hand-off for a consumer
    that runs phases after the loop, e.g. swebench SELECT)."""

    round: int
    slot: int


class Exhausted(Struct, frozen=True):
    """Every round's candidates failed validation and the round budget is spent — the give-up terminal."""

    rounds: int
