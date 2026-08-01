"""Observation contract for fanout_review (sprint 137).

CI path: a throwaway git repo gives `changed_files` a real diff; DeterministicResponders drive
the panel so the record is reproducible with no network. Asserts the diff is gathered read-only,
the panel reviews it, the quorum fires the judge, and the run finalises — the workflow's own
record is the evidence.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from substrate import api
from substrate.adapters import DeterministicResponder
from substrate.topologies.code_review import DEFAULT_ROLES
from substrate.topologies.workflows import changed_files, fanout_review_topology


def _repo_with_change(root: Path) -> Path:
    repo = root / "repo"
    repo.mkdir()
    for cmd in (
        ["git", "init", "-q", str(repo)],
        ["git", "-C", str(repo), "config", "user.email", "t@t"],
        ["git", "-C", str(repo), "config", "user.name", "t"],
    ):
        subprocess.run(cmd, check=True)
    (repo / "calc.py").write_text("def divide(a, b):\n    return a / b\n")
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "init"], check=True)
    # a change to review, uncommitted (diff vs HEAD)
    (repo / "calc.py").write_text("def divide(a, b):\n    return a / b  # no zero guard\n")
    return repo


def test_changed_files_gathers_the_diff_readonly(tmp_path: Path) -> None:
    repo = _repo_with_change(tmp_path)
    diff = changed_files(repo, ref="HEAD")
    assert "calc.py" in diff and "no zero guard" in diff  # the real change is gathered
    # read-only: the working tree still has the uncommitted change, git status unchanged
    status = subprocess.run(
        ["git", "-C", str(repo), "status", "--porcelain"], capture_output=True, text=True
    ).stdout
    assert "calc.py" in status  # gathering did not stage/commit/clean anything


def test_changed_files_empty_diff_is_a_marker_not_a_crash(tmp_path: Path) -> None:
    repo = _repo_with_change(tmp_path)
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "change"], check=True)
    diff = changed_files(repo, ref="HEAD")  # nothing uncommitted now
    assert "no changes" in diff.lower()


def test_fanout_review_reviews_the_diff_and_finalises(tmp_path: Path) -> None:
    repo = _repo_with_change(tmp_path)
    responders = {r: DeterministicResponder(seed=i) for i, r in enumerate(DEFAULT_ROLES)}
    topo = fanout_review_topology(
        repo,
        ref="HEAD",
        responders=responders,
        judge=DeterministicResponder(seed=99),
        quorum=3,
    )
    import asyncio

    result = asyncio.run(api.Runtime(tmp_path / "run").run(topo))
    assert result.status == "finalised"  # the runtime's own verdict, not inferred from the tail
    events = list(api.read_record(tmp_path / "run"))
    kinds = [e["kind"] for e in events]

    # the panel reviewed and the judge adjudicated on the gathered diff
    assert kinds.count("CritiquePosted") == len(DEFAULT_ROLES)
    assert "VerdictRendered" in kinds
    verdict = next(e for e in events if e["kind"] == "VerdictRendered")
    assert verdict["payload"]["n_critiques"] >= 3  # the quorum was met
    # the workflow's own record reaches a terminal — it is replayable evidence
    assert kinds[-1] == "substrate.RunFinalised"
    # composition, not new vocabulary: no invented kinds beyond code_review's + lifecycle
    assert not any(
        k not in {"CritiquePosted", "VerdictRendered"} and not k.startswith("substrate.")
        for k in kinds
    )


def test_non_repo_path_raises_not_swallowed(tmp_path: Path) -> None:
    with pytest.raises(subprocess.CalledProcessError):
        changed_files(tmp_path / "not-a-repo", ref="HEAD")
