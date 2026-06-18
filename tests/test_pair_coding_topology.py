"""Pair coding topology — CI MODE structural tests (Sprint 131).

Deterministic driver + navigator, asserting the wiring: the driver streams chunks in
instantiations, the navigator reviews each chunk (never itself), its Suggestion is staged
(substrate.InjectionApplied) and reaches the driver's NEXT instantiation's resolved input.
"""

import pytest

from substrate.api import Runtime, read_record
from substrate.reference._models import DeterministicResponder
from substrate.topologies.pair_coding import pair_coding_topology

CHUNKS = ["def solve(x):\n", "    y = x + 1\n", "    return y\n"]


def _topo():
    return pair_coding_topology(
        "write solve()",
        driver_model=DeterministicResponder(seed=1),
        navigator_model=DeterministicResponder(seed=2),
        chunks=CHUNKS,
        deterministic=True,
    )


@pytest.mark.timeout(15)
async def test_chunked_instantiation_count(tmp_path):
    result = await Runtime(tmp_path / "run").run(_topo())
    assert result.status == "finalised"
    envs = list(read_record(tmp_path / "run"))
    code_chunks = [e for e in envs if e["kind"] == "CodeChunk"]
    assert len(code_chunks) == len(CHUNKS)  # one chunk per canned chunk, no over/under-firing
    assert [e["payload"]["chunk_index"] for e in code_chunks] == list(range(len(CHUNKS)))
    driver_starts = [
        e
        for e in envs
        if e["kind"] == "substrate.ProducerStarted" and e["payload"]["producer"]["kind"] == "driver"
    ]
    assert len(driver_starts) == len(CHUNKS)  # one driver instantiation per chunk written
    assert envs[-1]["kind"] == "substrate.RunFinalised"


@pytest.mark.timeout(15)
async def test_navigator_does_not_subscribe_to_self(tmp_path):
    await Runtime(tmp_path / "run").run(_topo())
    envs = list(read_record(tmp_path / "run"))
    # the navigator fires once per CodeChunk and never on its own Suggestion (no self-feedback):
    # navigator instantiations == CodeChunk count, and Suggestions == CodeChunk count.
    nav_starts = sum(
        1
        for e in envs
        if e["kind"] == "substrate.ProducerStarted"
        and e["payload"]["producer"]["kind"] == "navigator"
    )
    n_chunks = sum(1 for e in envs if e["kind"] == "CodeChunk")
    n_sugg = sum(1 for e in envs if e["kind"] == "Suggestion")
    assert nav_starts == n_chunks == n_sugg == len(CHUNKS)
    # to-navigator only ever subscribes to CodeChunk, so every navigator firing cites a CodeChunk.
    nav_fires = [
        e
        for e in envs
        if e["kind"] == "substrate.TriggerFired"
        and e["payload"].get("trigger_id") == "to-navigator"
    ]
    assert len(nav_fires) == len(CHUNKS)


@pytest.mark.timeout(15)
async def test_suggestion_reaches_next_chunk_input(tmp_path):
    await Runtime(tmp_path / "run").run(_topo())
    envs = list(read_record(tmp_path / "run"))
    # the Suggestion was staged into the driver's input slot (recorded as InjectionApplied)...
    injections = [e for e in envs if e["kind"] == "substrate.InjectionApplied"]
    assert injections, "the navigator's Suggestion must be staged via the Route (InjectionApplied)"
    # ...and the next driver instantiation's RECORDED resolved input carries the staged suggestion.
    next_fires = [
        e
        for e in envs
        if e["kind"] == "substrate.TriggerFired" and e["payload"].get("trigger_id") == "next-chunk"
    ]
    assert next_fires, "the navigator's Suggestion must gate the driver's next chunk"
    assert all(f["payload"]["resolved_input"].get("suggestions") is not None for f in next_fires)
    # the suggestion that reached chunk N+1 carries the anchor_seq of the chunk it reviewed.
    carried = next_fires[0]["payload"]["resolved_input"]["suggestions"]
    assert "anchor_seq" in carried and "rationale" in carried
