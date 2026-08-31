"""swebench_solver — a vanilla non-agentic SWE-bench solver as a Substrate topology.

Design: `docs/swebench/swebench-solver-design.md`. Three plain phases, no tool use: LOCALIZE (issue + repo ->
suspect files -> edit locations) -> REPAIR (best-of-N SEARCH/REPLACE, apply to a clone, git diff ->
candidate patch; the shared best-of-N + correction loop reused from coding_flow) -> SELECT (repo-derived
regression + a generated reproduction test -> rerank -> one model_patch). Graded by the proven
`assay/swebench.py` oracle.

Built sprint-by-sprint under SDD (process/sprints/sprint-133+). The record vocabulary is locked in
`process/signals/swebench-solver-vocabulary.md`; the SEARCH/REPLACE applier (the measurement-critical
component) is `applier.py`.
"""

from __future__ import annotations

from .records import (
    AppliedPatch,
    Candidate,
    Draft,
    EditLocations,
    Exhausted,
    Reproduction,
    SelectedPatch,
    Solved,
    SuspectElements,
    SuspectFiles,
    TestResults,
    Verdict,
)

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
