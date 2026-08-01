"""Observation contract for best_of_n_verified (sprint 138, workflow-parity W1.2).

CI: a DeterministicResponder drafter + a deterministic `check` (the substrate-preferred verifier,
no model in the validator slot) drive the loop reproducibly with no network. Asserts the three
outcomes the composed best_of_n loop produces — Solved, Exhausted after correction, and the
independent-judge-model verify branch — on the workflow's own replayable record.
"""

from __future__ import annotations

import asyncio

from substrate import api
from substrate.adapters import DeterministicResponder
from substrate.topologies.workflows import best_of_n_verified_topology


def _run(topo, tmp_path):
    result = asyncio.run(api.Runtime(tmp_path / "run").run(topo))
    events = list(api.read_record(tmp_path / "run"))
    return result, events, [e["kind"] for e in events]


def test_a_passing_candidate_is_selected(tmp_path) -> None:
    topo = best_of_n_verified_topology(
        "name a prime number",
        drafter=DeterministicResponder(seed=0),
        verify=lambda response: (True, "accepted"),  # deterministic check, always passes
        n=3,
        max_rounds=2,
    )
    result, events, kinds = _run(topo, tmp_path)
    assert result.status == "finalised"  # the runtime's own verdict
    assert kinds.count("Candidate") == 3  # N drafted in round 1
    assert kinds.count("Verdict") == 3
    assert all(e["payload"]["passed"] for e in events if e["kind"] == "Verdict")
    assert "Solved" in kinds and "Exhausted" not in kinds
    assert kinds[-1] == "substrate.RunFinalised"
    # composition only — no invented vocabulary beyond best_of_n's records + lifecycle
    known = {"Draft", "Candidate", "Verdict", "Solved", "Exhausted", "ModelUsage"}
    assert not any(k not in known and not k.startswith("substrate.") for k in kinds)


def test_all_fail_then_correction_then_exhausted(tmp_path) -> None:
    topo = best_of_n_verified_topology(
        "an impossible task",
        drafter=DeterministicResponder(seed=0),
        verify=lambda response: (False, "rejected"),  # nothing ever passes
        n=2,
        max_rounds=2,
    )
    result, events, kinds = _run(topo, tmp_path)
    assert result.status == "finalised"
    # a failed round 1 feeds a correction round 2: n candidates per round, two rounds
    assert kinds.count("Candidate") == 4
    assert {e["payload"]["round"] for e in events if e["kind"] == "Candidate"} == {1, 2}
    assert "Exhausted" in kinds and "Solved" not in kinds
    assert kinds[-1] == "substrate.RunFinalised"


def test_independent_judge_model_verify_branch(tmp_path) -> None:
    # verify is a Responder (an INDEPENDENT judge, finding #42) — not a callable check. A menu of
    # one PASS reply makes the judge deterministically accept, exercising the model-verify parse.
    topo = best_of_n_verified_topology(
        "explain recursion in one sentence",
        drafter=DeterministicResponder(seed=1),
        verify=DeterministicResponder(seed=2, menu=["PASS: correct and complete"]),
        n=2,
        max_rounds=1,
    )
    result, events, kinds = _run(topo, tmp_path)
    assert result.status == "finalised"
    assert kinds.count("Verdict") == 2
    assert all(e["payload"]["passed"] for e in events if e["kind"] == "Verdict")
    assert "Solved" in kinds
