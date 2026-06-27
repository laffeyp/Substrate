"""SELECT — the swebench solver's selection phase (sprint 139).

Reranks the round's AppliedPatches by the solver's OWN test results into one SelectedPatch. The selection
LOGIC here is PURE and DETERMINISTIC given the recorded TestResults (design §4): it is replayable. Only
the test EXECUTION that produces TestResults — running the repo-DERIVED regression set + a generated
reproduction test in the instance container — is the run-and-observe Docker seam (`replayable=False`), a
SEPARATE component (`select_exec.py`, sprint 140).

Agentless's rerank: filter to regression-passing, prefer reproduction-resolved, majority-vote on the
normalized patch, deterministic tiebreak. Fall back to regression-only when no candidate passes reproduction.
"""

from __future__ import annotations

from collections import Counter

from .records import AppliedPatch, Reproduction, SelectedPatch, TestResults


def normalize_patch(model_patch: str) -> str:
    """Coarse normalization for majority voting: drop diff hunk-headers (`@@ ...`) + git `index ` lines +
    trailing whitespace, so two patches differing only in context-line bookkeeping vote together. (v1; a
    fuller AST-normalize of the RESULTING files — Agentless's approach — is a later refinement.)"""
    keep = [
        ln.rstrip()
        for ln in model_patch.splitlines()
        if not ln.startswith("@@") and not ln.startswith("index ")
    ]
    return "\n".join(keep).strip()


def select_patch(applied: list[AppliedPatch], results: dict[int, TestResults]) -> SelectedPatch | None:
    """Pick one patch, deterministically GIVEN `results`. Filter to regression-passing (fall back to ALL
    applied if none pass — 'regression-only' was empty); among those prefer `reproduction == RESOLVED`;
    then majority-vote on the normalized patch, lowest-slot tiebreak. None if no patch applied."""
    if not applied:
        return None
    reg_ok = [a for a in applied if (r := results.get(a.slot)) is not None and r.regression_passed]
    pool = reg_ok or applied
    resolved = [
        a for a in pool if (r := results.get(a.slot)) is not None and r.reproduction == Reproduction.RESOLVED
    ]
    candidates = resolved or pool
    norm = {a.slot: normalize_patch(a.model_patch) for a in candidates}
    counts = Counter(norm.values())
    top = counts.most_common(1)[0][0]
    winner = min((a for a in candidates if norm[a.slot] == top), key=lambda a: a.slot)
    r = results.get(winner.slot)
    reason = (
        f"regression={'pass' if winner in reg_ok else 'none-passed-fallback'}; "
        f"reproduction={r.reproduction.value if r is not None else 'n/a'}; "
        f"votes={counts[top]}/{len(candidates)}"
    )
    return SelectedPatch(slot=winner.slot, model_patch=winner.model_patch, reason=reason)
