# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Natural-conversation ablation — the emergence delta is the demo (Wave 13).

Same two thin speakers, same question. WITHOUT instruments: only Turn events — two parallel
monologues. WITH instruments: common ground accretes and a repair detector fires as a
side-effect of every turn, both Routed back into the speakers, so the turns themselves differ.
The delta — not either run alone — is the demonstration of composition.
"""

import pytest

from substrate.api import Runtime, first_divergence, read_record
from substrate.topologies.natural_conversation import natural_conversation_topology


@pytest.mark.timeout(20)
async def test_ablation_delta(tmp_path):
    await Runtime(tmp_path / "bare").run(
        natural_conversation_topology(instruments=False, max_rounds=3)
    )
    await Runtime(tmp_path / "rich").run(
        natural_conversation_topology(instruments=True, max_rounds=3)
    )
    bare = list(read_record(tmp_path / "bare"))
    rich = list(read_record(tmp_path / "rich"))

    # bare run: only the conversation, no instrument events
    assert not [e for e in bare if e["kind"] in ("CommonGround", "Repair")]
    # rich run: common ground accretes + repair fires as a side-effect of every turn
    assert [e for e in rich if e["kind"] == "CommonGround"]
    assert [e for e in rich if e["kind"] == "Repair"]
    # the requires-repair Route reached a speaker's recorded input (the emergence wiring)
    next_fires = [
        e
        for e in rich
        if e["kind"] == "substrate.TriggerFired"
        and str(e["payload"].get("trigger_id", "")).startswith("after-")
    ]
    assert any(f["payload"]["resolved_input"].get("repair") is not None for f in next_fires)

    # same turn COUNT either way, but the instrumented turns DIFFER (the instruments fed in)
    bare_turns = [e["payload"]["text"] for e in bare if e["kind"] == "Turn"]
    rich_turns = [e["payload"]["text"] for e in rich if e["kind"] == "Turn"]
    assert len(bare_turns) == len(rich_turns) == 6
    assert bare_turns != rich_turns  # the delta: instruments change the conversation


@pytest.mark.timeout(20)
async def test_both_arms_are_deterministic(tmp_path):
    # both the bare and the instrumented (multi-side-Producer) runs must be D-8 log-equivalent
    # across independent runs — determinism must survive the added concurrency.
    for arm in (False, True):
        await Runtime(tmp_path / f"{arm}a").run(
            natural_conversation_topology(instruments=arm, max_rounds=3)
        )
        await Runtime(tmp_path / f"{arm}b").run(
            natural_conversation_topology(instruments=arm, max_rounds=3)
        )
        assert first_divergence(tmp_path / f"{arm}a", tmp_path / f"{arm}b") is None, arm
