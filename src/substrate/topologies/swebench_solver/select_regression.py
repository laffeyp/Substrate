# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
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

THE FIREWALL (precise — review #69): this is firewall-clean on test SELECTION-BY-CONTENT and on the solver's
localize/repair — the candidate `model_patch` and the repo `test_files` come from the CHECKOUT, never the
PASS_TO_PASS field, and the eval_script's test selection is never reused. It is HARNESS-ASSISTED on the
regression FILE-SET: `exclude` is the held-out `test_patch` file PATHS (grade metadata — path-only, never
reaching the solver, so not a teach-to-the-test leak), used to drop issue-related test files that PROXIMITY
MISSES (non-co-located). That modestly spares a correct patch from a test a self-contained solver couldn't
know to skip. `exclude_delta` measures exactly how often that assist bites per instance, so the advantage is
disclosed, not silent (don't report a flat "firewall-clean" rate). A separate runtime filter (passed-at-base)
is applied where the tests actually run; this module only chooses WHICH test files are eligible.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from typing import Any, NamedTuple

from .select_docker import build_regression_command


class RegressionRun(NamedTuple):
    """A candidate's firewall-clean regression run: the in-container `command` plus the test `files` it
    actually runs (its scope). `files` lets the passed-at-base check be SCOPE-AWARE — a base-passing test
    that VANISHES from a file the candidate DID run is a regression (collection break, #70), while a
    base-passing test in a file the candidate didn't run is legitimately absent, not charged. `files=None`
    means an unscoped/static command (tests only)."""

    command: str
    files: frozenset[str] | None


def is_test_module(path: str) -> bool:
    """A pytest-collectable test MODULE — basename `test_*.py` or `*_test.py`. NOT support files under a
    test tree (`__init__.py`, fixture apps like flask's `tests/test_apps/cliapp/importerrorapp.py`, which
    raises ImportError ON PURPOSE). The real-runner smoke (review #69 NET #2) proved 'every file under
    tests/' poisons the run with collection errors — the regression set must be actual test modules, which
    is also why swebench's eval names specific files, never a directory."""
    base = os.path.basename(path)
    if not base.endswith(".py") or base == "__init__.py":
        return False
    return base.startswith("test_") or base.endswith("_test.py")


def canonical_test_modules(test_modules: list[str] | set[str]) -> list[str]:
    """Keep only the modules under the package's DOMINANT test directory — its own suite. Repos ship
    EXAMPLE/tutorial test trees (flask's `examples/*/tests/`) whose `conftest.py` imports an uninstalled
    example package -> a FATAL conftest ImportError that `--continue-on-collection-errors` can't survive
    (pytest exits rc 4 before running anything), zeroing the regression set (proven by the real solve #152).
    Group by the top path segment and keep the largest group (flask: `tests`=21 beats `examples`=5).
    Sorted, deterministic. (A coarse v1; a repo splitting its OWN suite across top dirs would lose the
    smaller part — tolerable for a selector input, refine per-repo if a target needs it.)"""
    mods = list(test_modules)
    if not mods:
        return []
    counts: dict[str, int] = {}
    for p in mods:
        counts[p.split("/")[0]] = counts.get(p.split("/")[0], 0) + 1
    top = max(sorted(counts), key=lambda k: counts[k])  # sorted() first -> deterministic tie-break
    return sorted(p for p in mods if p.split("/")[0] == top)


def discover_test_modules(repo_files: list[str] | set[str]) -> list[str]:
    """Filter a repo file listing (from `git ls-files`, the checkout) down to pytest-collectable test
    modules under the package's canonical test directory — the eligible universe the proximity picker
    chooses from. Sorted, deterministic."""
    return canonical_test_modules([p for p in repo_files if is_test_module(p)])


def patch_touched_files(model_patch: str) -> set[str]:
    """The repo-relative paths a unified git diff modifies, from its `--- a/` / `+++ b/` headers
    (`/dev/null` dropped — a pure add or delete still names the real side). Deterministic; order-free."""
    out: set[str] = set()
    for ln in model_patch.splitlines():
        for prefix in ("--- a/", "+++ b/"):
            if ln.startswith(prefix):
                path = ln[len(prefix) :].strip()
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
        base = base[len("test_") :]
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


def exclude_delta(
    test_files: list[str] | set[str], touched: set[str], *, exclude: set[str]
) -> list[str]:
    """The harness-assist `exclude` actually provides for this instance (review #69): the test files that
    proximity would have KEPT in the regression set but `exclude` (held-out test_patch paths) drops. Empty
    => proximity already caught the issue tests and the test_patch metadata changed nothing; non-empty =>
    these are correct-patch-sparing drops a self-contained solver couldn't know to make. Bank it alongside
    recall so any harness advantage in the resolve rate is disclosed with a number, never silent."""
    proximity_kept = set(test_files) - related_test_files(test_files, touched)
    return sorted(proximity_kept & set(exclude))


def make_regression_planner(
    spec: Mapping[str, Any],
    repo_test_files: list[str] | set[str],
    *,
    exclude: set[str],
) -> Callable[[str], RegressionRun]:
    """A PER-CANDIDATE regression planner: given a candidate's `model_patch`, pick the proximity regression
    set (repo tests minus the ones this patch is near, minus the held-out `exclude`) and build the
    firewall-clean in-container command from the repo `spec` (env-setup + test runner only). Each candidate
    gets a command tailored to what IT changed (review #65's 'not in a file/dir the candidate patch
    touches'). `repo_test_files` + the patch both come from the checkout — never PASS_TO_PASS."""
    files = list(repo_test_files)

    def plan(model_patch: str) -> RegressionRun:
        touched = patch_touched_files(model_patch)
        regression = proximity_regression_files(files, touched, exclude=exclude)
        return RegressionRun(build_regression_command(spec, regression), frozenset(regression))

    return plan
