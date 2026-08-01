"""fanout_review — the code-review panel on a REAL git diff (application-parity W1.1).

The agent-CLI "fan out a review over the changed files" pattern is `code_review_topology`
already: N role reviewers in parallel, a quorum-gated judge, cancel-all-others. The only
missing piece was real input. `changed_files` gathers a repo's diff (read-only git); the
topology hands it to the existing panel untouched. No engine change, no new vocabulary.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable, Mapping
from pathlib import Path

from ... import api
from ...adapters import Responder
from ..code_review import DEFAULT_ROLES, code_review_topology

# Bound the gathered diff so a large changeset cannot blow the reviewer prompt (the tool-result
# byte-cap lesson: an oversized payload is truncated with a visible marker, never sent whole).
_MAX_DIFF_CHARS = 24_000


def changed_files(repo: str | Path, ref: str = "HEAD~1") -> str:
    """The changed files between `ref` and the working tree, as one review-ready string.

    Read-only: runs `git -C <repo> diff` variants and nothing that mutates the repo. Covers BOTH
    tracked changes (`git diff <ref>`) AND new untracked files (`git diff --no-index /dev/null
    <file>`) — a new file is the most review-worthy change there is, and a bare `git diff <ref>`
    silently omits it (review F-6). Returns a bounded unified diff; no changes yields an honest
    no-op marker (not a crash). A non-repo path or a bad ref raises CalledProcessError — the caller
    surfaces it, it is not swallowed.
    """
    repo = Path(repo).expanduser()
    tracked = subprocess.run(
        ["git", "-C", str(repo), "diff", ref],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    # untracked (new) files: git diff <ref> never lists them. Gather each as an addition diff.
    others = subprocess.run(
        ["git", "-C", str(repo), "ls-files", "--others", "--exclude-standard"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    new_blocks = []
    for f in others:
        # diff against /dev/null -> a "new file" addition diff; exit 1 means "differs" (normal), not error.
        block = subprocess.run(
            ["git", "-C", str(repo), "diff", "--no-index", "--", "/dev/null", f],
            capture_output=True,
            text=True,
            check=False,
        ).stdout
        if block:
            new_blocks.append(block)
    out = "\n".join([tracked, *new_blocks]).strip()
    if not out:
        return f"(no changes between {ref} and the working tree in {repo}, and no new files)"
    if len(out) > _MAX_DIFF_CHARS:
        out = (
            out[:_MAX_DIFF_CHARS]
            + f"\n\n[diff truncated at {_MAX_DIFF_CHARS} chars — narrow the ref]"
        )
    return out


def fanout_review_topology(
    repo: str | Path,
    *,
    responders: Mapping[str, Responder],
    judge: Responder,
    ref: str = "HEAD~1",
    roles: tuple[str, ...] = DEFAULT_ROLES,
    quorum: int = 3,
    deterministic: bool = True,
    slow_roles: frozenset[str] = frozenset(),
    linger_seconds: float = 0.0,
) -> Callable[[api.TopologyBuilder], None]:
    """A review panel over the changed files of `repo` at `ref`. Gathers the diff, then returns
    the existing `code_review_topology` fed that diff — composition, not reimplementation. The
    signature mirrors `code_review_topology` (`responders` role->Responder, `judge`, `quorum`,
    `deterministic`); `repo`/`ref` are the only additions. Raises if `repo` is not a git repo.
    """
    code = changed_files(repo, ref)
    # F-7: clamp the quorum to the panel size. `quorum` defaults to 3, but `roles` is caller-set; a
    # 2-role panel with the default quorum would post 2 critiques, never reach 3, and finalise with NO
    # VerdictRendered — the same silent-no-answer class. A quorum can never exceed the number of reviewers
    # that will ever post, so clamp it here rather than leaving the guard to the caller.
    effective_quorum = min(quorum, len(roles)) if roles else quorum
    return code_review_topology(
        code,
        responders=responders,
        judge=judge,
        roles=roles,
        quorum=effective_quorum,
        deterministic=deterministic,
        slow_roles=slow_roles,
        linger_seconds=linger_seconds,
    )
