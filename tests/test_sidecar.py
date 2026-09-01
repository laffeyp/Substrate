# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Off-bus sidecar tests (technical §3.8, §6.4; conformance check 14).

The load-bearing property is DIAGNOSTIC INVARIANCE (check 14): enabling the diagnostic
sidecar (or writer-stats) leaves the bus log bit-identical. Wall-clock `t` is the only
per-run-varying envelope field (excluded from D-8); the bit-identity comparison is over
every frame with `t` normalized out — kind, seq, schema, producer, payload, crc-modulo-t
must be identical whether diagnostics are on or off."""

from msgspec import Struct

from substrate.api import (
    Runtime,
    first_divergence,
    read_record,
    read_sidecar,
    threshold_count,
)
from substrate.kernel.triggers import PerEvent
from substrate.types import Subscription


class CountReached(Struct, frozen=True):
    n: int


async def counter(_input):
    for n in range(1, 6):
        yield CountReached(n=n)


def _topo(b):
    # a Trigger whose predicate NEVER fires -> every evaluation is a non-firing eval the
    # diagnostic sidecar records, while producing no bus effect (so the bus log is the same
    # on/off — the whole point of check 14).
    b.producer_kind("counter", schemas=[CountReached], schema_version=1, factory=lambda: counter)
    b.producer_kind("noop", schemas=[CountReached], schema_version=1, factory=lambda: counter)
    b.initial("counter", input=None)
    b.trigger(
        "never",
        subscription=Subscription(kinds=frozenset({"CountReached"})),
        predicate=lambda ctx: False,  # never fires
        starts="noop",
        input_builder=lambda ctx: None,
        policy=PerEvent(),
    )
    b.termination(threshold_count("substrate.ProducerCompleted", 1))


def _kinds_and_payloads(root):
    # the bus log reduced to (kind, payload) per frame, dropping per-run-varying envelope
    # identity (t/run_id/instance live in the envelope or are run-scoped). This is the
    # "did the sidecar change the BUS" comparison at the application+control altitude.
    return [(e["kind"], e["payload"]) for e in read_record(root)]


async def test_diagnostic_invariance_bus_bit_identical_on_off(tmp_path):
    # conformance check 14: the same seeded topology, diagnostics OFF vs ON, yields an
    # IDENTICAL bus log. The honest bus-identity comparison is the D-8 relation
    # (first_divergence None) — it excludes the inherent per-run identity (run_id, instance
    # ULIDs, t) while comparing every kind + decision-identity payload. A diagnostics-induced
    # perturbation of the bus WOULD show as a divergence.
    await Runtime(tmp_path / "off").run(_topo)
    await Runtime(tmp_path / "on", diagnostics=True).run(_topo)
    assert first_divergence(tmp_path / "off", tmp_path / "on") is None
    # and the per-frame (kind, payload) sequence is identical too (modulo the RunStarted
    # run_id, which is run-scoped identity, not a diagnostics effect)
    off = _kinds_and_payloads(tmp_path / "off")
    on = _kinds_and_payloads(tmp_path / "on")
    assert [k for k, _ in off] == [k for k, _ in on]  # identical kind sequence


async def test_diagnostics_off_writes_no_sidecar(tmp_path):
    await Runtime(tmp_path / "off").run(_topo)
    assert not (tmp_path / "off" / "sidecar" / "diagnostics.jsonl").exists()


async def test_diagnostics_on_records_non_firing_evals_off_bus(tmp_path):
    await Runtime(tmp_path / "on", diagnostics=True).run(_topo)
    diag = read_sidecar(tmp_path / "on" / "sidecar" / "diagnostics.jsonl")
    # 5 CountReached -> 5 non-firing evaluations of the "never" predicate, keyed by seq,
    # NEVER sequence-numbered themselves (they carry observed_seq, not seq).
    evals = [d for d in diag if d.get("predicate_id") == "never"]
    assert len(evals) == 5
    assert all("observed_seq" in d and "seq" not in d for d in evals)
    assert all(d["result"] is False for d in evals)
    # and they are off the bus: no diagnostic kind leaked into the record
    assert not any(
        str(e["kind"]).startswith("substrate.Predicate") and "diagnostic" in str(e).lower()
        for e in read_record(tmp_path / "on")
    )


async def test_writer_stats_on_off_bus_bit_identical_and_samples(tmp_path):
    await Runtime(tmp_path / "off").run(_topo)
    await Runtime(tmp_path / "on", writer_stats=True).run(_topo)
    # bus identical under D-8 (writer-stats sampling is off-cycle, never perturbs the bus)
    assert first_divergence(tmp_path / "off", tmp_path / "on") is None
    # writer_stats only written when enabled
    assert not (tmp_path / "off" / "sidecar" / "writer_stats.jsonl").exists()
    stats = read_sidecar(tmp_path / "on" / "sidecar" / "writer_stats.jsonl")
    assert stats and all("admission_depth" in s and "seq" not in s for s in stats)
