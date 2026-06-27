"""SELECT regression-set choice — the firewall-clean, deterministic test picker (finding 17b, review #65).

The problem (review #65): at base_commit the repo's existing tests encode the OLD (buggy) behavior, and
the fixed-behavior tests (FAIL_TO_PASS) are absent. So "run every existing test" PENALIZES a correct patch
that intentionally changes buggy-but-tested behavior — those tests fail though the patch is right. A naive
"passed-before -> must-pass-after" baseline has the same flaw. The fix (Agentless's step) is to use as the
regression set only the tests UNRELATED to the issue.

This v1 is a DETERMINISTIC proximity heuristic, not a model call (review #65: the regression set is a
SELECTOR input, not the grade — a mis-pick lowers selection quality but can't poison the oracle verdict, so
don't over-engineer; make a model picker a MEASURED upgrade later, same recall@k discipline). A test file is
"related to the change" — and therefore EXCLUDED from the regression set — if any of:
  - the candidate patch touches it directly (it's a test the fix edits),
  - it shares a directory with a file the patch touches,
  - its name stem matches a touched source file's stem (test_blueprints.py ~ src/flask/blueprints.py) — the
    common test<->module pairing, the signal directory alone misses when tests live in a separate tree.

THE FIREWALL: the candidate `model_patch` and the repo `test_files` both come from the CHECKOUT — never the
instance's PASS_TO_PASS field (grade metadata). The held-out `test_patch` files are dropped via `exclude`,
so a FAIL_TO_PASS test that happens to live in a pre-existing file can never enter the regression set. A
separate runtime filter (passed-at-base) is applied where the tests actually run; this module only chooses
WHICH test files are eligible.
"""

from __future__ import annotations

import os


def patch_touched_files(model_patch: str) -> set[str]:
    """The repo-relative paths a unified git diff modifies, from its `--- a/` / `+++ b/` headers
    (`/dev/null` dropped — a pure add or delete still names the real side). Deterministic; order-free."""
    out: set[str] = set()
    for ln in model_patch.splitlines():
        for prefix in ("--- a/", "+++ b/"):
            if ln.startswith(prefix):
                path = ln[len(prefix):].strip()
                if path and path != "dev/null":
                    out.add(path)
    return out


def _module_stem(path: str) -> str:
    """The comparison stem of a path: basename, drop a `.py`, drop a leading `test_` / trailing `_test`.
    So `tests/test_blueprints.py`, `src/flask/blueprints.py`, and `blueprints_test.py` all stem to
    `blueprints` — the test<->module pairing the directory check alone misses."""
    base = os.path.basename(path)
    if base.endswith(".py"):
        base = base[:-3]
    if base.startswith("test_"):
        base = base[len("test_"):]
    elif base.endswith("_test"):
        base = base[: -len("_test")]
    return base


def related_test_files(test_files: list[str] | set[str], touched: set[str]) -> set[str]:
    """The repo test files 'near the change' (per the module docstring's three signals) — the set to
    EXCLUDE from the regression run because a correct patch may legitimately change their behavior."""
    touched_dirs = {os.path.dirname(p) for p in touched}
    touched_stems = {_module_stem(p) for p in touched}
    related: set[str] = set()
    for tf in test_files:
        if tf in touched:
            related.add(tf)
        elif os.path.dirname(tf) in touched_dirs:
            related.add(tf)
        elif _module_stem(tf) in touched_stems:
            related.add(tf)
    return related


def proximity_regression_files(
    test_files: list[str] | set[str], touched: set[str], *, exclude: set[str]
) -> list[str]:
    """The firewall-clean regression set: repo test files MINUS the change-related ones MINUS the held-out
    `test_patch` files (`exclude`). Sorted (deterministic). `test_files` and `touched` both come from the
    CHECKOUT — never PASS_TO_PASS."""
    related = related_test_files(test_files, touched)
    return sorted(tf for tf in test_files if tf not in related and tf not in exclude)
