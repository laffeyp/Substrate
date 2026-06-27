"""Observation contract for the SELECT logic (sprint 139) — pure + deterministic given recorded
TestResults (design §4). The rerank: regression filter, reproduction preference, majority vote, fallback."""

from substrate.topologies.swebench_solver.records import AppliedPatch, Reproduction, TestResults
from substrate.topologies.swebench_solver.select import normalize_patch, select_patch


def _ap(slot: int, patch: str = "diff", rnd: int = 1) -> AppliedPatch:
    return AppliedPatch(round=rnd, slot=slot, model_patch=patch, creates_file=False)


def _tr(slot: int, reg: bool, repro: Reproduction) -> TestResults:
    return TestResults(slot=slot, regression_passed=reg, reproduction=repro, summary="")


def test_empty_returns_none() -> None:
    assert select_patch([], {}) is None


def test_prefers_reproduction_resolved() -> None:
    applied = [_ap(0, "A"), _ap(1, "B")]
    results = {0: _tr(0, True, Reproduction.OTHER), 1: _tr(1, True, Reproduction.RESOLVED)}
    sel = select_patch(applied, results)
    assert sel is not None and sel.slot == 1 and sel.model_patch == "B"


def test_excludes_regression_failures() -> None:
    # slot 0 RESOLVED the issue but BREAKS regression -> excluded; slot 1 passes regression -> wins.
    applied = [_ap(0, "A"), _ap(1, "B")]
    results = {0: _tr(0, False, Reproduction.RESOLVED), 1: _tr(1, True, Reproduction.OTHER)}
    sel = select_patch(applied, results)
    assert sel is not None and sel.slot == 1


def test_majority_vote_lowest_slot_tiebreak() -> None:
    # two identical patches (slots 1,2) + one different (slot 0); all pass regression, none resolved.
    applied = [_ap(0, "X"), _ap(1, "SAME"), _ap(2, "SAME")]
    results = {s: _tr(s, True, Reproduction.OTHER) for s in (0, 1, 2)}
    sel = select_patch(applied, results)
    assert sel is not None and sel.model_patch == "SAME" and sel.slot == 1  # 2 votes, lowest-slot tiebreak


def test_fallback_when_none_pass_regression() -> None:
    applied = [_ap(0, "A"), _ap(1, "B")]
    results = {0: _tr(0, False, Reproduction.OTHER), 1: _tr(1, False, Reproduction.OTHER)}
    sel = select_patch(applied, results)
    assert sel is not None and "none-passed-fallback" in sel.reason  # regression-only was empty


def test_normalize_patch_drops_hunk_noise() -> None:
    p = "diff --git a/m.py b/m.py\nindex abc..def 100644\n@@ -1,3 +1,3 @@\n-old\n+new  \n"
    n = normalize_patch(p)
    assert "@@" not in n and "index " not in n and "+new" in n
