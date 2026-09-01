# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Adversarial pair — CI structural + bound + determinism tests (Wave 13)."""

import pytest

from substrate.api import Runtime, first_divergence, read_record
from substrate.topologies.adversarial_pair import adversarial_pair_topology


@pytest.mark.timeout(15)
async def test_bounded_refinement_loop(tmp_path):
    result = await Runtime(tmp_path / "run").run(adversarial_pair_topology(max_attempts=3))
    assert result.status == "finalised"
    envs = list(read_record(tmp_path / "run"))
    artifacts = [e for e in envs if e["kind"] == "Artifact"]
    challenges = [e for e in envs if e["kind"] == "Challenge"]
    assert [a["payload"]["version"] for a in artifacts] == [0, 1, 2, 3]  # v0 + 3 refinements
    assert len(challenges) == 4
    # the refine Trigger fired exactly max_attempts times (the bound holds — no runaway)
    refine = [
        e
        for e in envs
        if e["kind"] == "substrate.TriggerFired" and e["payload"].get("trigger_id") == "refine"
    ]
    assert len(refine) == 3
    # the challenge was Routed into the writer's next instantiation (InjectionApplied + resolved)
    assert [e for e in envs if e["kind"] == "substrate.InjectionApplied"]
    assert all(f["payload"]["resolved_input"].get("challenge") is not None for f in refine)
    assert envs[-1]["kind"] == "substrate.RunFinalised"


@pytest.mark.timeout(15)
async def test_adversarial_pair_is_deterministic(tmp_path):
    await Runtime(tmp_path / "a").run(adversarial_pair_topology(max_attempts=4))
    await Runtime(tmp_path / "b").run(adversarial_pair_topology(max_attempts=4))
    assert first_divergence(tmp_path / "a", tmp_path / "b") is None
