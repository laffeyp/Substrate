# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""The SWE-bench workspace adapter — turn ANY topology's edits to a repo checkout into a model_patch.

This is the whole bridge between "a topology that codes" and SWE-bench: the topology changes a checkout of
the repo at base_commit (however it codes), and `git diff` of the checkout IS the patch the official grader
runs. It is environment-independent — the official harness (`run_swebench`) applies the diff in its OWN
fresh container, so the diff STRING is the only thing that crosses the boundary. Two backends fill the
workspace and both end here at `workspace_diff`: a host clone (`host_clone`, this module) and a live
instance container (later). The topology never needs to know anything about SWE-bench.

DROP THE GRADE'S TEST FILES (the sharp gotcha + the inflation guard): the grader re-applies the held-out
`test_patch` ON TOP of the model_patch and re-runs the graded tests. A topology's edit to a graded test
file is BANNED two ways: (1) a file `test_patch` also touches collides at apply time → false not-resolved;
(2) a file holding a graded test could be WEAKENED → a false resolve. The SEMANTIC drop set is the files
`test_patch` touches (`graded_test_files`); a name-based `is_test_file` is a backstop for pre-existing test
files the model shouldn't touch (incl. Django's bare `tests.py`). Build/config edits are KEPT —
a real fix may legitimately touch setup.py/pyproject. Dropping only ever DEFLATES a patch, never fakes one.
"""

from __future__ import annotations

import re
import subprocess
import tempfile

# pytest + unittest/django test FILES at any depth: test_*.py, *_test.py, tests.py/test.py, conftest.py.
# NB: deliberately NOT "anything under tests/" — django ships `django/test/` as SOURCE (the test-framework
# utilities), so a directory match would false-drop legitimate fixes. The authoritative drop set is
# `graded_test_files`; this filename match only backstops pre-existing test files test_patch doesn't touch.
_TEST_FILE = re.compile(r"(^|/)(test_[^/]*\.py|[^/]*_test\.py|tests?\.py|conftest\.py)$")
# the `diff --git` header b-side path, all three forms git emits: bare `a/X b/Y`, both-sides
# C-quoted `"a/X" "b/Y"`, and MIXED — either side quoted independently. Git quotes any side that
# needs escaping (spaces, non-ASCII), so a rename that changes only one side's special-char status
# emits a mixed-quote header. F8 fix (review 2026-08-08): pre-fix regex covered bare-both and
# quoted-both only; a mixed-quote rename dropped from filter_diff and the model_patch graded
# not-resolved. A header that matches NONE is treated as unparseable (caller fails safe).
_HDR_A = r'(?:a/(\S+)|"a/(.+?)")'
_HDR_B = r'(?:b/(\S+)|"b/(.+?)")'
_HDR = re.compile(rf"^diff --git {_HDR_A} {_HDR_B}$")


def _section_b_path(header_line: str) -> str | None:
    """The b-side path of a `diff --git` header, or None if the header can't be parsed (caller fails safe)."""
    line = header_line.rstrip("\n")
    m = _HDR.match(line)
    if not m:
        return None
    # The b-side is captured either at group 3 (bare) or group 4 (quoted); at most one is set.
    return m.group(3) or m.group(4)


def is_test_file(path: str) -> bool:
    """A test file whose edits are dropped from the model_patch — a NAME-BASED backstop (a collision with
    the held-out test_patch is a false not-resolved; weakening a graded test is a false resolve). Catches
    pytest names AND django's bare `tests.py`. The authoritative drop set is `graded_test_files`; this guards
    pre-existing test files test_patch doesn't touch."""
    return _TEST_FILE.search(path) is not None


def graded_test_files(test_patch: str) -> set[str]:
    """The files the held-out `test_patch` touches — the SEMANTIC, ground-truth set of graded-test files the
    model_patch must not carry edits to (so the harness's apply of test_patch never collides, and the model
    can't have weakened a graded test). Parsed from the diff's `--- a/` / `+++ b/` headers (`/dev/null`
    dropped). This is harness-side, path-only metadata — the solver never sees it."""
    out: set[str] = set()
    for ln in test_patch.splitlines():
        for prefix in ("--- a/", "+++ b/"):
            if ln.startswith(prefix):
                p = ln[len(prefix) :].strip()
                if p and p != "dev/null":
                    out.add(p)
    return out


def filter_diff(diff: str, *, drop_files: frozenset[str] = frozenset()) -> str:
    """Drop the per-file sections of a unified git diff that touch a graded-test file: any path in
    `drop_files` (the test_patch set — authoritative) OR matching `is_test_file` (the name backstop). A git
    diff is a sequence of `diff --git a/<p> b/<p>` sections; keep only the non-test sections."""
    if not diff.strip():
        return diff
    out: list[str] = []
    keep = True
    for line in diff.splitlines(keepends=True):
        if line.startswith("diff --git "):
            path = _section_b_path(line)
            # FAIL SAFE: an UNPARSEABLE header (e.g. a quoted path we didn't anticipate) DROPS the section
            # — never inherit the previous keep-state, which would let a graded-test edit survive (review #71).
            keep = path is not None and path not in drop_files and not is_test_file(path)
        if keep:
            out.append(line)
    return "".join(out)


def workspace_diff(
    repo_dir: str, *, base_ref: str = "HEAD", drop_files: frozenset[str] = frozenset()
) -> str:
    """The model_patch from a changed checkout: `git add -A` (so new files show) then `git diff --cached`
    against `base_ref`, with graded-test-file sections dropped (`drop_files` = the instance's test_patch
    files; plus the name backstop). Empty string if nothing (non-test) changed — an empty patch grades
    not-resolved, never a crash. The single diff seam both backends call."""
    subprocess.run(["git", "-C", repo_dir, "add", "-A"], capture_output=True, check=False)
    diff = subprocess.run(
        ["git", "-C", repo_dir, "diff", "--cached", base_ref],
        capture_output=True,
        text=True,
        check=False,
    )
    return filter_diff(diff.stdout, drop_files=drop_files)


def host_clone(source: str, base_commit: str) -> str:
    """A HOST clone of `source` (a local path or a git URL) checked out at `base_commit`, with the `origin`
    remote REMOVED — the host-backend contamination guard (no upstream the topology could `git fetch` the
    fixing commit from). Returns the clone dir; the caller cleans it up. Env-gated (git, and network for a
    URL source)."""
    d = tempfile.mkdtemp(prefix="swe-ws-")
    subprocess.run(["git", "clone", "--quiet", source, d], check=True)
    subprocess.run(["git", "-C", d, "checkout", "--quiet", base_commit], check=True)
    subprocess.run(["git", "-C", d, "remote", "remove", "origin"], capture_output=True, check=False)
    return d


__all__ = ["is_test_file", "graded_test_files", "filter_diff", "workspace_diff", "host_clone"]
