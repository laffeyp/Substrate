# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Grader instrument — the cheap-talk loop closes (Grade events on the bus → scored payoff)."""

import pytest

from substrate.api import Runtime, read_record
from substrate.reference._models import DeterministicResponder
from substrate.topologies.conversation import Instrument, conversation_topology
from substrate.topologies.instruments.grader import Grade, grader_factory, score_grades
from substrate.topologies.instruments.scoring import select_scoring_rule


def _grader_instrument() -> Instrument:
    # the grader composed as an instrument (the caller-side composition the engine now expects).
    return Instrument(
        "grader",
        [Grade],
        grader_factory(DeterministicResponder(seed=999)),
        lambda ctx: {
            "round": int(ctx.event.payload["round"]),
            "prior_turns": list(ctx.views["transcript"].value()),
        },
    )


@pytest.mark.timeout(15)
async def test_grader_emits_grades_and_they_score(tmp_path):
    topo = conversation_topology(
        [DeterministicResponder(seed=0), DeterministicResponder(seed=1)],
        max_rounds=3,
        instruments=[_grader_instrument()],
    )
    await Runtime(tmp_path / "run").run(topo)
    envs = list(read_record(tmp_path / "run"))
    grades = [e["payload"] for e in envs if e["kind"] == "Grade"]
    # a grade per turn after the first (the grader fires on every Turn, skips the empty first)
    assert len(grades) >= 5
    for g in grades:
        assert 0.0 <= g["prior_confidence"] <= 1.0
        assert g["observed_outcome"] in (0.0, 1.0)
    # the durable Grade events convert to a per-claim payoff under a proper rule (Brier here)
    losses = score_grades(grades, select_scoring_rule("brier"))
    # VALUE assertion, not just range (review #22 T5): each claim's Brier loss must equal
    # (confidence - outcome)^2, independently recomputed — catches a scorer that returns a
    # constant (e.g. 0.0), which a range check `0<=v<=1` would let pass.
    expected = {
        g["claim"]: (float(g["prior_confidence"]) - float(g["observed_outcome"])) ** 2
        for g in grades  # last-write per claim, matching score_grades' dict semantics
    }
    assert losses == pytest.approx(expected)
    assert any(v > 0.0 for v in losses.values())  # a real scorer is not all-zero
    assert envs[-1]["kind"] == "substrate.RunFinalised"


@pytest.mark.timeout(15)
async def test_scoring_off_emits_no_grades(tmp_path):
    topo = conversation_topology(
        [DeterministicResponder(seed=0), DeterministicResponder(seed=1)], max_rounds=2
    )
    await Runtime(tmp_path / "run").run(topo)
    assert not [e for e in read_record(tmp_path / "run") if e["kind"] == "Grade"]
