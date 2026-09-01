# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""`substrate score` — the calibration payoff is surfaced as a result (review #18)."""

import re

import pytest
from click.testing import CliRunner

from substrate.api import Runtime
from substrate.cli import EXIT_OK, main
from substrate.topologies.debate import debate_topology
from substrate.topologies.natural_conversation import natural_conversation_topology


@pytest.mark.timeout(15)
async def test_score_surfaces_per_speaker_calibration(tmp_path):
    # an instrumented conversation grades each turn (Grade events); `score` computes the loss.
    await Runtime(tmp_path / "nc").run(
        natural_conversation_topology(instruments=True, max_rounds=3)
    )
    res = CliRunner().invoke(main, ["score", str(tmp_path / "nc")])
    assert res.exit_code == EXIT_OK, res.output
    assert "calibration loss (brier" in res.output
    # VALUE assertion (review #22 T5): a real scorer produces a nonzero loss, not all mean=0.0000.
    means = [float(m) for m in re.findall(r"mean=([\d.]+)", res.output)]
    assert means and max(means) > 0.0


@pytest.mark.timeout(15)
async def test_score_errors_without_grades(tmp_path):
    await Runtime(tmp_path / "d").run(debate_topology())  # no scoring -> no Grade events
    res = CliRunner().invoke(main, ["score", str(tmp_path / "d")])
    assert res.exit_code != EXIT_OK
    assert "no Grade events" in res.output


@pytest.mark.timeout(15)
async def test_score_unknown_rule_errors(tmp_path):
    await Runtime(tmp_path / "nc").run(
        natural_conversation_topology(instruments=True, max_rounds=2)
    )
    res = CliRunner().invoke(main, ["score", str(tmp_path / "nc"), "--rule", "nonesuch"])
    assert res.exit_code != EXIT_OK
    assert "unknown scoring rule" in res.output
