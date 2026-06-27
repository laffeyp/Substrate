"""The SWE-bench workspace adapter — turn ANY topology's edits to a repo checkout into a model_patch.

This is the whole bridge between "a topology that codes" and SWE-bench: the topology changes a checkout of
the repo at base_commit (however it codes), and `git diff` of the checkout IS the patch the official grader
runs. It is environment-independent — the official harness (`run_swebench`) applies the diff in its OWN
fresh container, so the diff STRING is the only thing that crosses the boundary. Two backends fill the
workspace and both end here at `workspace_diff`: a host clone (`host_clone`, this module) and a live
instance container (later). The topology never needs to know anything about SWE-bench.

DROP TEST-FILE EDITS (the sharp gotcha): the grader re-applies the held-out `test_patch` ON TOP of the
model_patch; if the patch touches a test file the test_patch also touches, the apply collides and the
instance errors out as a FALSE not-resolved. So a SWE-bench patch must never carry a topology's edits to
test files. (Build/config edits are KEPT — a real fix may legitimately touch setup.py/pyproject.)
"""

from __future__ import annotations

import re
import subprocess
import tempfile

# pytest test files: test_*.py, *_test.py, conftest.py (at any directory depth).
_TEST_FILE = re.compile(r"(^|/)(test_[^/]*\.py|[^/]*_test\.py|conftest\.py)$")
_DIFF_HEADER = re.compile(r"^diff --git a/(\S+) b/(\S+)")


def is_test_file(path: str) -> bool:
    """A pytest test file whose edits must be dropped from the model_patch (the grader re-applies the
    held-out test_patch on top — a collision there is a false not-resolved)."""
    return _TEST_FILE.search(path) is not None


def filter_diff(diff: str) -> str:
    """Drop the per-file sections of a unified git diff that touch TEST files. A git diff is a sequence of
    `diff --git a/<p> b/<p>` sections; keep only the sections whose path is not a test file."""
    if not diff.strip():
        return diff
    out: list[str] = []
    keep = True
    for line in diff.splitlines(keepends=True):
        m = _DIFF_HEADER.match(line)
        if m:
            keep = not is_test_file(m.group(2))
        if keep:
            out.append(line)
    return "".join(out)


def workspace_diff(repo_dir: str, *, base_ref: str = "HEAD") -> str:
    """The model_patch from a changed checkout: `git add -A` (so new files show) then `git diff --cached`
    against `base_ref`, with test-file sections dropped. Empty string if nothing (non-test) changed — an
    empty patch grades not-resolved, never a crash. The single diff seam both backends call."""
    subprocess.run(["git", "-C", repo_dir, "add", "-A"], capture_output=True, check=False)
    diff = subprocess.run(
        ["git", "-C", repo_dir, "diff", "--cached", base_ref],
        capture_output=True, text=True, check=False,
    )
    return filter_diff(diff.stdout)


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


__all__ = ["is_test_file", "filter_diff", "workspace_diff", "host_clone"]
