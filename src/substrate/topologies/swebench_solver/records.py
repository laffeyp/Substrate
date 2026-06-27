"""swebench_solver records — the locked vocabulary (sprint 133), as frozen Structs.

Vocabulary doc: `process/signals/swebench-solver-vocabulary.md`. Registered in WORKING_AGREEMENT.

The shared best-of-N + correction records (`Draft`, `Candidate`, `Verdict`, `Solved`, `Exhausted`) are
REUSED from coding_flow as the canonical 3-consumer contract (review #57 / #58 — verified byte-for-byte;
NOT re-rolled). This module re-exports them and adds the swebench-specific LOCALIZE / REPAIR-bridge /
SELECT records that wrap the shared loop. Collections are `tuple[...]` (a frozen record's fields are
immutable — the locked vocab's `list[str]` is realized as `tuple[str, ...]` for hash/encode stability).
"""

from __future__ import annotations

import enum

from msgspec import Struct

# The shared 3-consumer best-of-N + correction contract. Canonical home: coding_flow (until the sprint-4
# Wave-0 extraction moves it to a shared module and updates both importers). Re-exported here so the
# swebench topology reads them from its own namespace.
from ..coding_flow import Candidate, Draft, Exhausted, Solved, Verdict

__all__ = [
    "Draft",
    "Candidate",
    "Verdict",
    "Solved",
    "Exhausted",
    "SuspectFiles",
    "SuspectElements",
    "EditLocations",
    "AppliedPatch",
    "Reproduction",
    "TestResults",
    "SelectedPatch",
]


# --- LOCALIZE (before the loop) ---


class SuspectFiles(Struct, frozen=True):
    """File-level localization output (LLM-on-repo-skeleton). Observable: recall@k vs the gold-patch
    files (==1.0 on the flask-4045 fixture)."""

    files: tuple[str, ...]


class SuspectElements(Struct, frozen=True):
    """Class/function localization within one suspect file."""

    file: str
    elements: tuple[str, ...]


class EditLocations(Struct, frozen=True):
    """Fine-grained edit targets (`file::element` or `file:line-range`) — the REPAIR loop's input. The
    Repairer's input_builder composes these into the shared `Draft.context` (sprint 5)."""

    targets: tuple[str, ...]


# --- REPAIR -> SELECT bridge (the deterministic apply output) ---


class AppliedPatch(Struct, frozen=True):
    """A candidate that applied cleanly, carrying its `git diff` (`model_patch`) and whether it created a
    new file (the empty-SEARCH path, design §4b). `round`+`slot` complete the lineage. The REPAIR->SELECT
    bridge: SELECT reranks over the AppliedPatches."""

    round: int
    slot: int
    model_patch: str
    creates_file: bool


# --- SELECT (after the loop) ---


class Reproduction(enum.Enum):
    """The reproduction test's three-state outcome — enforced at the speaker's mouth (#2), not by string
    convention."""

    REPRODUCED = "reproduced"
    RESOLVED = "resolved"
    OTHER = "other"


class TestResults(Struct, frozen=True):
    """The solver's own validation of one applied patch: repo-DERIVED regression result (NOT the
    PASS_TO_PASS grade field — firewall) + reproduction-test status. A run-and-observe Docker seam
    (design §4) — captured once, `replayable=False` at the producer that emits it."""

    slot: int
    regression_passed: bool
    reproduction: Reproduction
    summary: str


class SelectedPatch(Struct, frozen=True):
    """The final submitted patch + why it won (majority vote / regression / reproduction). Deterministic
    GIVEN the recorded TestResults. The topology's output to the swebench oracle."""

    slot: int
    model_patch: str
    reason: str
