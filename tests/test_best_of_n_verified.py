"""Observation contract for best_of_n_verified (sprint 138, application-parity W1.2).

CI: a DeterministicResponder drafter + a deterministic `check` (the substrate-preferred verifier,
no model in the validator slot) drive the loop reproducibly with no network. Asserts the three
outcomes the composed best_of_n loop produces — Solved, Exhausted after correction, and the
independent-judge-model verify branch — on the workflow's own replayable record.
"""

from __future__ import annotations

import asyncio

from substrate import api
from substrate.adapters import DeterministicResponder
from substrate.topologies.applications import best_of_n_verified_topology
from substrate.topologies.applications.best_of_n_verified import _verdict_passed


class _RaisingResponder:
    """A model that fails on every call — the flaky seam a real deployment hits (F-4)."""

    def respond(self, prompt: str) -> str:
        raise RuntimeError("model unreachable")


class _SpyResponder:
    """Records prompts, returns a fixed reply — asserts what the model actually SAW (F-11)."""

    def __init__(self, reply: str = "an answer") -> None:
        self.prompts: list[str] = []
        self._reply = reply

    def respond(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self._reply


def _run(topo, tmp_path):
    result = asyncio.run(api.Runtime(tmp_path / "run").run(topo))
    events = list(api.read_record(tmp_path / "run"))
    return result, events, [e["kind"] for e in events]


def test_the_task_reaches_the_drafter_and_the_candidate_reaches_the_judge(tmp_path) -> None:
    # F-11: no test proved the task text reaches the drafter or the candidate reaches the verifier —
    # blanking either (best_of_n_verified.py:37/60) left the suite green. Spies on both seams prove it.
    drafter = _SpyResponder(reply="the mitochondria is the powerhouse of the cell")
    judge = _SpyResponder(reply="PASS: correct")
    topo = best_of_n_verified_topology(
        "state one fact about cell biology",
        drafter=drafter,
        verify=judge,
        n=1,
        max_rounds=1,
    )
    _run(topo, tmp_path)
    assert any("cell biology" in p for p in drafter.prompts)  # the TASK reached the drafter
    # the judge prompt carries BOTH the task and the drafter's candidate answer (what it must verify)
    assert any("cell biology" in p and "powerhouse" in p for p in judge.prompts)


def test_verdict_parse_is_robust_to_preamble_and_fails_closed() -> None:
    # F-9: startswith("PASS") failed a correct candidate whenever the judge preambled. Take the FIRST
    # PASS/FAIL token; fail closed when neither is present (a verifier must not pass what it can't confirm).
    assert (
        _verdict_passed("Sure, my verdict: PASS. It is correct.")[0] is True
    )  # preamble before PASS
    assert _verdict_passed("FAIL — the answer is wrong")[0] is False
    assert (
        _verdict_passed("PASS on correctness, though it could FAIL on style")[0] is True
    )  # PASS first
    assert _verdict_passed("This would FAIL; only later could it PASS")[0] is False  # FAIL first
    ok, reason = _verdict_passed("I am not sure about this one")  # neither token
    assert ok is False and "unparseable" in reason  # fail closed, legibly


def test_a_failed_drafter_still_finalises_not_a_stall(tmp_path) -> None:
    # F-4: a drafter call that raises must still emit a Candidate, or the slot produces no Verdict, the
    # judge never sees n verdicts, and the round stalls to a silent no-answer. Prove it reaches a terminal.
    topo = best_of_n_verified_topology(
        "any task",
        drafter=_RaisingResponder(),  # every draft fails
        verify=lambda response: ("draft failed" not in response, "checked"),
        n=2,
        max_rounds=1,
    )
    result, events, kinds = _run(topo, tmp_path)
    assert result.status == "finalised"  # did NOT stall
    assert kinds.count("Candidate") == 2  # one per slot even though every draft failed
    assert all(
        "draft failed" in e["payload"]["response"] for e in events if e["kind"] == "Candidate"
    )
    assert kinds.count("Verdict") == 2 and "Exhausted" in kinds  # verified and reached a terminal


def test_a_failed_judge_model_still_produces_a_verdict(tmp_path) -> None:
    # F-4 (verify seam): a judge Responder that raises must still emit a Verdict (failed), not stall.
    topo = best_of_n_verified_topology(
        "explain something",
        drafter=DeterministicResponder(seed=1),
        verify=_RaisingResponder(),  # the judge model is down
        n=2,
        max_rounds=1,
    )
    result, events, kinds = _run(topo, tmp_path)
    assert result.status == "finalised"
    assert kinds.count("Verdict") == 2
    assert all(not e["payload"]["passed"] for e in events if e["kind"] == "Verdict")
    assert all("verify failed" in e["payload"]["summary"] for e in events if e["kind"] == "Verdict")


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
    # F-18: BOTH the draft and the verify model calls are metered (2 drafts + 2 judge calls), so the
    # "verified with an independent judge" claim is checkable from the record, not just the prose.
    assert kinds.count("ModelUsage") == 4
